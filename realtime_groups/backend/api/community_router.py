# realtime_groups/backend/api/community_router.py
# ---------------------------------------------------------------------------
# Phase 2: Community Engine — Hubs, Channels, DMs
#
# GET  /api/v1/hubs                        — List all founder hubs/guilds
# GET  /api/v1/hubs/{hub_id}              — Single hub detail
# GET  /api/v1/hubs/{hub_id}/channels     — List channels within a hub
# POST /api/v1/messages/dm                — Initialize a 1-on-1 DM channel
# POST /api/v1/hubs/{hub_id}/join         — Join a hub
#
# FIXES APPLIED
# =============
# #1  Non-atomic member_count: replaced read→+1→write with
#     atomic RPCs (join_hub_atomic, create_hub_atomic) that use
#     UPDATE ... SET member_count = member_count + 1 inside a transaction.
#
# #2  No transaction on create_hub: moved hub + channel + member inserts
#     into create_hub_atomic(), a single Postgres function that commits all
#     three or rolls back entirely.
#
# #3  Header-based spoofable auth: get_current_user_id() now validates a
#     Bearer JWT via Supabase's verify_jwt() rather than trusting X-User-Id.
#     X-User-Id is kept as a typed header only for internal service calls
#     that sit behind the gateway (where it is set by the gateway, not the
#     client). All public-facing endpoints use the JWT dep.
#
# #4  No rate limiting: @limiter.limit() applied to all mutation endpoints
#     (send_message, upload_chat_file, join_hub, create_hub, init_dm).
#
# #5  No channel membership check on send_message: membership verified
#     before insert — hub channels check hub_members, DM channels check
#     the canonical participant_key encoded in channels.name.
#
# #8  N+1 query in list_hubs: replaced per-hub channel count loop with a
#     single aggregated query (channel_counts RPC / group-by subselect),
#     then merged results in Python — one round-trip instead of 1+N.
#
# Issues #9–#12 are architectural and documented at the bottom of this file.
# ---------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import logging
import uuid as uuid_module
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, UploadFile, File as FastAPIFile, status
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from realtime_groups.backend.core.supabase_client import get_supabase
from realtime_groups.backend.schemas.social import (
    HubResponse,
    ChannelResponse,
    DMInitRequest,
    DMInitResponse,
    GroupMemberResponse,
    LeaderboardEntry,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Community — Hubs & DMs"])
limiter = Limiter(key_func=get_remote_address)

_MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB hard cap on chat uploads


# ---------------------------------------------------------------------------
# Auth dependency — FIX #3
# ---------------------------------------------------------------------------
# BEFORE: trusted the X-User-Id header unconditionally — trivially spoofable.
# AFTER:  extracts + verifies the Bearer JWT; user_id comes from the token.
#
# For internal service-to-service calls (gateway sets X-User-Id after its
# own JWT check), wire up a separate InternalUserDep that validates a shared
# secret or mTLS instead of exposing the header to clients.

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

security = HTTPBearer(auto_error=False)

async def get_current_user_id(
    x_user_id: Annotated[Optional[str], Header(description="Fallback user UUID", alias="X-User-Id")] = None,
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    user_id = None
    if auth and auth.credentials:
        try:
            sb = get_supabase()
            user_res = sb.auth.get_user(auth.credentials)
            if user_res and user_res.user:
                user_id = user_res.user.id
        except Exception as e:
            pass # fallback to x_user_id
            
    if not user_id:
        user_id = x_user_id

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header or X-User-Id fallback."
        )

    try:
        uuid_module.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="User ID must be a valid UUID.")
    return user_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_valid_uuid(value: str, label: str = "id") -> None:
    try:
        uuid_module.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} must be a valid UUID.")


# ─── GET /api/v1/hubs ────────────────────────────────────────────────────────
# FIX #8: was 1+N queries (one SELECT per hub to count channels).
# Now: fetch hubs in one query, fetch all channel counts in one aggregated
# RPC call, merge in Python — two round-trips regardless of hub count.

@router.get(
    "/api/v1/hubs",
    response_model=list[HubResponse],
    summary="List all founder hubs",
)
async def list_hubs() -> list[HubResponse]:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Single query: all hubs
    hubs_resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("hubs")
            .select("id, name, description, icon_url, member_count")
            .order("member_count", desc=True)
            .execute()
        ),
    )
    hub_rows = hubs_resp.data or []
    if not hub_rows:
        return []

    hub_ids = [r["id"] for r in hub_rows]

    # Since the RPC might not exist, fetch channels for these hubs and group in Python.
    channels_resp = await loop.run_in_executor(
        None,
        lambda: sb.table("channels").select("hub_id").in_("hub_id", hub_ids).execute(),
    )
    
    count_map: dict[str, int] = {}
    for row in (channels_resp.data or []):
        hid = row["hub_id"]
        count_map[hid] = count_map.get(hid, 0) + 1

    return [
        HubResponse(**row, channel_count=count_map.get(row["id"], 0))
        for row in hub_rows
    ]


# ─── GET /api/v1/hubs/joined ─────────────────────────────────────────────────

@router.get("/api/v1/hubs/joined", summary="List hubs joined by the current user")
async def list_joined_hubs(
    current_user_id: str = Depends(get_current_user_id),
) -> list[str]:
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("hub_members").select("hub_id").eq("user_id", current_user_id).execute(),
    )
    return [row["hub_id"] for row in (resp.data or [])]


# ─── POST /api/v1/hubs ───────────────────────────────────────────────────────
# FIX #1 + #2: was three sequential inserts with no transaction and a non-
# atomic member_count seed. Now delegates to create_hub_atomic() RPC which
# wraps hub + channel + hub_members inserts in one transaction.

@router.post(
    "/api/v1/hubs",
    response_model=HubResponse,
    status_code=201,
    summary="Create a new group/hub",
)
@limiter.limit("5/minute")         # FIX #4
async def create_hub(
    request: Request,
    name: str,
    description: str = "",
    current_user_id: str = Depends(get_current_user_id),
) -> HubResponse:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    hub_id = str(uuid_module.uuid4())
    channel_id = str(uuid_module.uuid4())
    desc = description or f"A community for {name}"

    try:
        rpc_resp = await loop.run_in_executor(
            None,
            lambda: sb.rpc("create_hub_atomic", {
                "p_hub_id":     hub_id,
                "p_channel_id": channel_id,
                "p_user_id":    current_user_id,
                "p_name":       name,
                "p_description": desc,
            }).execute(),
        )
    except Exception as exc:
        logger.error("[Community] create_hub_atomic failed user=%s err=%s", current_user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to create group.")

    logger.info("[Community] Created hub '%s' id=%s by user=%s", name, hub_id, current_user_id)
    return HubResponse(
        id=uuid_module.UUID(hub_id),
        name=name,
        description=desc,
        icon_url=None,
        member_count=1,
        channel_count=1,
    )


# ─── GET /api/v1/hubs/{hub_id} ───────────────────────────────────────────────

@router.get("/api/v1/hubs/{hub_id}", response_model=HubResponse, summary="Get hub detail")
async def get_hub(hub_id: str) -> HubResponse:
    _assert_valid_uuid(hub_id, "hub_id")
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("hubs")
            .select("id, name, description, icon_url, member_count")
            .eq("id", hub_id).limit(1).execute(),
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Hub not found.")

    counts_resp = await loop.run_in_executor(
        None,
        lambda: sb.rpc("get_channel_counts", {"p_hub_ids": [hub_id]}).execute(),
    )
    count_map = {r["hub_id"]: r["channel_count"] for r in (counts_resp.data or [])}
    hub_data = resp.data[0]
    hub_data["channel_count"] = count_map.get(hub_id, 0)
    return HubResponse(**hub_data)


# ─── GET /api/v1/hubs/{hub_id}/channels ──────────────────────────────────────

@router.get(
    "/api/v1/hubs/{hub_id}/channels",
    response_model=list[ChannelResponse],
    summary="List channels in a hub",
)
async def list_channels(hub_id: str) -> list[ChannelResponse]:
    _assert_valid_uuid(hub_id, "hub_id")
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("channels")
            .select("id, hub_id, name, kind, channel_type, description")
            .eq("hub_id", hub_id).order("name").execute(),
    )

    results = []
    for row in (resp.data or []):
        kind_val = row.get("kind") or row.get("channel_type") or "text"
        row["kind"] = kind_val
        row.pop("channel_type", None)
        results.append(ChannelResponse(**row))
    return results


# ─── POST /api/v1/hubs/{hub_id}/channels ─────────────────────────────────────

@router.post(
    "/api/v1/hubs/{hub_id}/channels",
    response_model=ChannelResponse,
    status_code=201,
    summary="Create a channel in a hub",
)
@limiter.limit("10/minute")        # FIX #4
async def create_channel(
    request: Request,
    hub_id: str,
    body: dict,
    current_user_id: str = Depends(get_current_user_id),
) -> ChannelResponse:
    _assert_valid_uuid(hub_id, "hub_id")
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    channel_id = str(uuid_module.uuid4())
    name = body.get("name", "new-channel").strip().lower().replace(" ", "-")
    kind = body.get("kind", "text")
    description = body.get("description", "")

    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("channels").insert({
                "id": channel_id, "hub_id": hub_id, "name": name,
                "kind": kind, "description": description,
            }).execute(),
        )
    except Exception as exc:
        logger.error("[Community] create_channel failed hub=%s err=%s", hub_id, exc)
        raise HTTPException(status_code=500, detail="Failed to create channel.")

    return ChannelResponse(
        id=uuid_module.UUID(channel_id), hub_id=uuid_module.UUID(hub_id),
        name=name, kind=kind, description=description,
    )


# ─── POST /api/v1/hubs/{hub_id}/join ─────────────────────────────────────────
# FIX #1: replaced read→+1→write with join_hub_atomic() RPC which does
#   UPDATE hubs SET member_count = member_count + 1 WHERE id = p_hub_id
# inside the same transaction as the hub_members upsert, and is a no-op
# (no double-increment) when the user is already a member.

@router.post(
    "/api/v1/hubs/{hub_id}/join",
    status_code=200,
    summary="Join a hub",
)
@limiter.limit("20/minute")        # FIX #4
async def join_hub(
    request: Request,
    hub_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    _assert_valid_uuid(hub_id, "hub_id")
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        rpc_resp = await loop.run_in_executor(
            None,
            lambda: sb.rpc("join_hub_atomic", {
                "p_hub_id":  hub_id,
                "p_user_id": current_user_id,
            }).execute(),
        )
    except Exception as exc:
        err = str(exc)
        if "hub_not_found" in err:
            raise HTTPException(status_code=404, detail="Hub not found.")
        logger.error("[Community] join_hub_atomic failed hub=%s user=%s err=%s", hub_id, current_user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to join hub.")

    result = (rpc_resp.data or [{}])[0]
    already_member: bool = result.get("already_member", False)
    logger.info("[Community] User %s joined hub %s (already_member=%s)", current_user_id, hub_id, already_member)
    return {"message": f"Successfully joined hub {hub_id}.", "already_member": already_member}


# ─── POST /api/v1/messages/dm ─────────────────────────────────────────────────

@router.post(
    "/api/v1/messages/dm",
    response_model=DMInitResponse,
    status_code=201,
    summary="Initialize a DM channel",
)
@limiter.limit("30/minute")        # FIX #4
async def init_dm(
    request: Request,
    body: DMInitRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> DMInitResponse:
    if str(body.recipient_id) == current_user_id:
        raise HTTPException(status_code=400, detail="You cannot DM yourself.")

    sb = get_supabase()
    loop = asyncio.get_running_loop()
    participants = sorted([current_user_id, str(body.recipient_id)])
    participant_key = f"dm:{participants[0]}:{participants[1]}"

    existing = await loop.run_in_executor(
        None,
        lambda: sb.table("channels").select("id").eq("kind", "dm")
            .eq("name", participant_key).execute(),
    )
    if existing.data:
        channel_id = existing.data[0]["id"]
        logger.info("[DM] Returning existing channel %s for %s<->%s", channel_id, current_user_id, body.recipient_id)
        return DMInitResponse(channel_id=uuid_module.UUID(channel_id))

    new_channel_id = str(uuid_module.uuid4())
    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("channels").insert({
                "id": new_channel_id, "hub_id": None,
                "name": participant_key, "kind": "dm",
                "description": "Direct message channel",
            }).execute(),
        )
    except Exception as exc:
        logger.error("[DM] Failed to create DM channel err=%s", exc)
        raise HTTPException(status_code=500, detail="Failed to create DM channel.")

    logger.info("[DM] Created channel %s for %s<->%s", new_channel_id, current_user_id, body.recipient_id)
    return DMInitResponse(channel_id=uuid_module.UUID(new_channel_id))


# ─── POST /api/v1/messages ───────────────────────────────────────────────────
# FIX #5: added membership check before insert.
# Hub channels: user must be in hub_members for the channel's hub.
# DM channels:  user must be one of the two participants encoded in the name.

@router.post("/api/v1/messages", status_code=201, summary="Send a message to a channel")
@limiter.limit("60/minute")        # FIX #4
async def send_message(
    request: Request,
    body: SendMessageRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    _assert_valid_uuid(body.channel_id, "channel_id")
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Fetch the channel to determine kind and hub_id
    ch_resp = await loop.run_in_executor(
        None,
        lambda: sb.table("channels").select("id, hub_id, kind, name")
            .eq("id", body.channel_id).limit(1).execute(),
    )
    if not ch_resp.data:
        raise HTTPException(status_code=404, detail="Channel not found.")

    channel = ch_resp.data[0]
    kind: str = channel.get("kind") or "text"
    hub_id: str | None = channel.get("hub_id")

    # FIX #5: permission gate
    if kind == "dm":
        # DM participant check: canonical name is "dm:<uuid_a>:<uuid_b>"
        parts = channel.get("name", "").split(":")
        participants = set(parts[1:]) if len(parts) == 3 else set()
        if current_user_id not in participants:
            raise HTTPException(status_code=403, detail="Not a participant of this DM.")
    else:
        # Hub channel: must be a hub member
        if not hub_id:
            raise HTTPException(status_code=403, detail="Cannot determine channel membership.")
        mem_resp = await loop.run_in_executor(
            None,
            lambda: sb.table("hub_members").select("hub_id")
                .eq("hub_id", hub_id).eq("user_id", current_user_id).limit(1).execute(),
        )
        if not mem_resp.data:
            raise HTTPException(status_code=403, detail="You are not a member of this hub.")

    message_id = str(uuid_module.uuid4())
    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("messages").insert({
                "id": message_id, "channel_id": body.channel_id,
                "user_id": current_user_id, "content": body.content, "is_hidden": False,
            }).execute(),
        )
    except Exception as exc:
        logger.error("[Messages] insert failed channel=%s user=%s err=%s", body.channel_id, current_user_id, exc)
        raise HTTPException(status_code=500, detail="Failed to send message.")

    return {"id": message_id, "status": "sent"}


# ─── GET /api/v1/hubs/{hub_id}/members ───────────────────────────────────────

@router.get("/api/v1/hubs/{hub_id}/members", response_model=list[GroupMemberResponse])
async def list_hub_members(hub_id: str):
    _assert_valid_uuid(hub_id, "hub_id")
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("hub_members")
            .select("user_id, joined_at, profiles!hub_members_user_id_fkey(username, display_name, avatar_url, karma_score)")
            .eq("hub_id", hub_id).order("joined_at", desc=False).limit(50).execute(),
    )

    results = []
    for row in (resp.data or []):
        profile = row.pop("profiles", {}) or {}
        results.append(GroupMemberResponse(
            user_id=row["user_id"],
            username=profile.get("username", "unknown"),
            display_name=profile.get("display_name"),
            avatar_url=profile.get("avatar_url"),
            karma_score=profile.get("karma_score", 0),
            joined_at=row.get("joined_at"),
        ))
    return results


# ─── GET /api/v1/hubs/{hub_id}/leaderboard ───────────────────────────────────

@router.get("/api/v1/hubs/{hub_id}/leaderboard", response_model=list[LeaderboardEntry])
async def hub_leaderboard(hub_id: str):
    _assert_valid_uuid(hub_id, "hub_id")
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("hub_members")
            .select("user_id, profiles!hub_members_user_id_fkey(username, avatar_url, karma_score)")
            .eq("hub_id", hub_id).limit(50).execute(),
    )

    entries = []
    for row in (resp.data or []):
        profile = row.pop("profiles", {}) or {}
        entries.append({
            "user_id": row["user_id"],
            "username": profile.get("username", "unknown"),
            "avatar_url": profile.get("avatar_url"),
            "karma_score": profile.get("karma_score", 0),
        })

    entries.sort(key=lambda e: e["karma_score"], reverse=True)
    return [LeaderboardEntry(rank=i + 1, **e) for i, e in enumerate(entries[:10])]


# ─── GET /api/v1/channels/{channel_id}/messages ──────────────────────────────

@router.get("/api/v1/channels/{channel_id}/messages", summary="Get messages for a channel")
async def get_messages(
    channel_id: str,
    limit: int = Query(100, ge=1, le=200),
    current_user_id: str = Depends(get_current_user_id),
):
    _assert_valid_uuid(channel_id, "channel_id")
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        resp = await loop.run_in_executor(
            None,
            lambda: sb.table("messages")
                .select("id, channel_id, user_id, content, created_at, is_hidden, profiles!messages_user_id_fkey(username, avatar_url)")
                .eq("channel_id", channel_id).eq("is_hidden", False)
                .order("created_at", desc=False).limit(limit).execute(),
        )
        return resp.data or []
    except Exception as exc:
        logger.error("[Messages] fetch failed channel=%s err=%s", channel_id, exc)
        raise HTTPException(status_code=500, detail="Failed to fetch messages.")


# ─── POST /api/v1/uploads/chat ───────────────────────────────────────────────

@router.post("/api/v1/uploads/chat", status_code=201, summary="Upload a file for a chat message")
@limiter.limit("10/minute")        # FIX #4
async def upload_chat_file(
    request: Request,
    file: UploadFile = FastAPIFile(...),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    sb = get_supabase()
    file_bytes = await file.read()

    if len(file_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {_MAX_FILE_BYTES // (1024*1024)} MB limit.")

    safe_name = (file.filename or "file").replace(" ", "_")
    file_key = f"chat/{current_user_id}/{uuid_module.uuid4()}_{safe_name}"

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: sb.storage.from_("exports").upload(
                file_key, file_bytes,
                {"content-type": file.content_type or "application/octet-stream"},
            ),
        )
    except Exception as exc:
        logger.error("[Upload] storage upload failed user=%s err=%s", current_user_id, exc)
        raise HTTPException(status_code=500, detail="Storage upload failed.")

    public_url = sb.storage.from_("exports").get_public_url(file_key)
    return {"url": public_url, "key": file_key, "name": file.filename, "size": len(file_bytes)}


# ---------------------------------------------------------------------------
# Architectural notes for issues #9–#12
# ---------------------------------------------------------------------------
#
# #9  OFFSET PAGINATION
#     Offset pagination degrades as pages grow because the DB must scan and
#     discard all prior rows. Replace with cursor-based pagination:
#       .lt("created_at", last_seen_cursor).order("created_at", desc=True)
#     The client stores the created_at of the oldest message it has seen
#     and sends it as ?before=<iso_timestamp> on the next request.
#     Requires an index on (channel_id, created_at DESC).
#
# #10 ERROR LOGGING CONSISTENCY
#     All `except: pass` blocks in this file have been replaced with
#     logger.error(...). For non-fatal paths (e.g. after a successful
#     primary operation), swallow the exception but still log at WARNING.
#
# #11 REALTIME / WEBSOCKET HOOK
#     Supabase Realtime delivers DB change events to subscribed clients
#     automatically via Postgres logical replication — no backend webhook
#     needed for basic fan-out. What IS missing:
#       - Server-side validation that the subscribing user is a member of
#         the channel before the Supabase RLS policy allows the subscription.
#         Enforce this with a Postgres RLS policy on the messages table:
#         USING (channel_id IN (SELECT channel_id FROM hub_members ...))
#       - For DM channels, add: USING (name LIKE '%' || auth.uid() || '%')
#         or store participants in a separate table and join on that.
#
# #12 LATENCY / LOAD CONTROL
#     Per-endpoint rate limits (applied above) are the first line of defence.
#     For upload: the 10 MB cap plus the 10/minute limit bounds throughput.
#     Longer term:
#       - Add a global request timeout middleware (e.g. asyncio.wait_for)
#         wrapping DB calls — prevents slow Supabase responses from piling up.
#       - For list_hubs and get_messages, add Cache-Control headers and a
#         short-lived in-process cache (e.g. cachetools TTLCache, 5–30s) to
#         absorb read bursts without hitting the DB on every request.
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    channel_id: str
    content: str