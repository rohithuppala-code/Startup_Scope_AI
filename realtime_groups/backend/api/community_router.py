# realtime_groups/backend/api/community_router.py
# ---------------------------------------------------------------------------
# Phase 2: Community Engine — Hubs, Channels, DMs
#
# GET  /api/v1/hubs                        — List all founder hubs/guilds
# GET  /api/v1/hubs/{hub_id}               — Single hub detail
# GET  /api/v1/hubs/{hub_id}/channels      — List channels within a hub
# POST /api/v1/messages/dm                 — Initialize a 1-on-1 DM channel
# POST /api/v1/hubs/{hub_id}/join          — Join a hub
# ---------------------------------------------------------------------------

import asyncio
import logging
import uuid as uuid_module
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status, UploadFile, File as FastAPIFile

from realtime_groups.backend.core.supabase_client import get_supabase
from realtime_groups.backend.schemas.social import (
    HubResponse,
    ChannelResponse,
    DMInitRequest,
    DMInitResponse,
    GroupMemberResponse,
    LeaderboardEntry,
)
from pydantic import BaseModel

class SendMessageRequest(BaseModel):
    channel_id: str
    content: str

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Community — Hubs & DMs"])


async def get_current_user_id(
    x_user_id: Annotated[str, Header(description="Authenticated user UUID")]
) -> str:
    try:
        uuid_module.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.")
    return x_user_id


# ─── GET /api/v1/hubs ────────────────────────────────────────────────────────

@router.get(
    "/api/v1/hubs",
    response_model=list[HubResponse],
    summary="List all founder hubs",
    description="Returns all public hubs (guilds) e.g. 'SaaS Builders', 'Deep Tech', 'Web3 Founders'.",
)
async def list_hubs() -> list[HubResponse]:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("hubs")
            .select("id, name, description, icon_url, member_count")
            .order("member_count", desc=True)
            .execute()
        ),
    )

    hubs = []
    for row in (resp.data or []):
        # Fetch channel count for each hub
        ch_resp = await loop.run_in_executor(
            None,
            lambda hub_id=row["id"]: (
                sb.table("channels")
                .select("id", count="exact")
                .eq("hub_id", hub_id)
                .execute()
            ),
        )
        row["channel_count"] = ch_resp.count or 0
        hubs.append(HubResponse(**row))

    return hubs

# ─── GET /api/v1/hubs/joined ──────────────────────────────────────────────────

@router.get(
    "/api/v1/hubs/joined",
    summary="List hubs joined by the current user",
)
async def list_joined_hubs(
    current_user_id: str = Depends(get_current_user_id),
) -> list[str]:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: sb.table("hub_members")
            .select("hub_id")
            .eq("user_id", current_user_id)
            .execute()
    )

    return [row["hub_id"] for row in (resp.data or [])]

# ─── POST /api/v1/hubs ──────────────────────────────────────────────────────

@router.post(
    "/api/v1/hubs",
    response_model=HubResponse,
    status_code=201,
    summary="Create a new group/hub",
    description="Creates a new founder hub with a default #general channel.",
)
async def create_hub(
    name: str,
    description: str = "",
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    hub_id = str(uuid_module.uuid4())
    channel_id = str(uuid_module.uuid4())

    try:
        # Create the hub
        await loop.run_in_executor(
            None,
            lambda: sb.table("hubs").insert({
                "id": hub_id,
                "name": name,
                "description": description or f"A community for {name}",
                "icon_url": None,
                "created_by": current_user_id,
                "member_count": 1,
            }).execute(),
        )

        # Create default #general channel
        await loop.run_in_executor(
            None,
            lambda: sb.table("channels").insert({
                "id": channel_id,
                "hub_id": hub_id,
                "name": "general",
                "kind": "text",
                "description": "General discussion",
            }).execute(),
        )

        # Add the creator as a member
        await loop.run_in_executor(
            None,
            lambda: sb.table("hub_members").insert({
                "hub_id": hub_id,
                "user_id": current_user_id,
            }).execute(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create group: {e}")

    logger.info("[Community] Created hub '%s' (id=%s) by user=%s", name, hub_id, current_user_id)
    return HubResponse(
        id=uuid_module.UUID(hub_id),
        name=name,
        description=description or f"A community for {name}",
        icon_url=None,
        member_count=1,
        channel_count=1,
    )


# ─── GET /api/v1/hubs/{hub_id} ───────────────────────────────────────────────

@router.get(
    "/api/v1/hubs/{hub_id}",
    response_model=HubResponse,
    summary="Get hub detail",
)
async def get_hub(hub_id: str) -> HubResponse:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        resp = await loop.run_in_executor(
            None,
            lambda: (
                sb.table("hubs")
                .select("id, name, description, icon_url, member_count")
                .eq("id", hub_id)
                .single()
                .execute()
            ),
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Hub not found.")
    if not resp.data:
        raise HTTPException(status_code=404, detail="Hub not found.")

    ch_resp = await loop.run_in_executor(
        None,
        lambda: sb.table("channels").select("id", count="exact").eq("hub_id", hub_id).execute(),
    )
    resp.data["channel_count"] = ch_resp.count or 0
    return HubResponse(**resp.data)


# ─── GET /api/v1/hubs/{hub_id}/channels ──────────────────────────────────────

@router.get(
    "/api/v1/hubs/{hub_id}/channels",
    response_model=list[ChannelResponse],
    summary="List channels in a hub",
    description="Returns text and voice channels for a given hub.",
)
async def list_channels(hub_id: str) -> list[ChannelResponse]:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("channels")
            .select("id, hub_id, name, kind, channel_type, description")
            .eq("hub_id", hub_id)
            .order("name")
            .execute()
        ),
    )

    results = []
    for row in (resp.data or []):
        # Normalise: DB has both 'kind' (preferred) and 'channel_type' (legacy).
        # Prefer 'kind' if set, fall back to 'channel_type', then default 'text'.
        kind_val = row.get("kind") or row.get("channel_type") or "text"
        row["kind"] = kind_val
        row.pop("channel_type", None)   # Remove legacy key so ChannelResponse is clean
        results.append(ChannelResponse(**row))
    return results


# ─── POST /api/v1/hubs/{hub_id}/channels ─────────────────────────────────────

@router.post(
    "/api/v1/hubs/{hub_id}/channels",
    response_model=ChannelResponse,
    status_code=201,
    summary="Create a channel in a hub",
)
async def create_channel(
    hub_id: str,
    body: dict,
    current_user_id: str = Depends(get_current_user_id),
):
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
                "id": channel_id,
                "hub_id": hub_id,
                "name": name,
                "kind": kind,
                "description": description,
            }).execute(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create channel: {e}")

    return ChannelResponse(
        id=uuid_module.UUID(channel_id),
        hub_id=uuid_module.UUID(hub_id),
        name=name,
        kind=kind,
        description=description,
    )


# ─── POST /api/v1/hubs/{hub_id}/join ─────────────────────────────────────────

@router.post(
    "/api/v1/hubs/{hub_id}/join",
    status_code=200,
    summary="Join a hub",
    description="Adds the current user as a member of the hub and increments member_count.",
)
async def join_hub(
    hub_id: str,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Check if already a member first — prevents double-counting member_count
    existing_resp = await loop.run_in_executor(
        None,
        lambda: sb.table("hub_members").select("hub_id")
            .eq("hub_id", hub_id).eq("user_id", current_user_id).execute()
    )
    already_member = bool(existing_resp.data)

    # Idempotent upsert — duplicate PK is fine
    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("hub_members").upsert({
                "hub_id": hub_id,
                "user_id": current_user_id,
            }).execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Only increment member_count if this is a NEW join (not a repeat call)
    if not already_member:
        try:
            hub_resp = await loop.run_in_executor(
                None,
                lambda: sb.table("hubs").select("member_count").eq("id", hub_id).single().execute()
            )
            if hub_resp.data:
                current_count = hub_resp.data.get("member_count", 0)
                await loop.run_in_executor(
                    None,
                    lambda: sb.table("hubs").update({"member_count": current_count + 1}).eq("id", hub_id).execute()
                )
        except Exception:
            pass  # Non-fatal

    logger.info("[Community] User %s joined hub %s (new=%s)", current_user_id, hub_id, not already_member)
    return {"message": f"Successfully joined hub {hub_id}.", "already_member": already_member}


# ─── POST /api/v1/messages/dm ─────────────────────────────────────────────────

@router.post(
    "/api/v1/messages/dm",
    response_model=DMInitResponse,
    status_code=201,
    summary="Initialize a DM channel",
    description=(
        "Creates (or retrieves) a 1-on-1 DM channel between two founders. "
        "The actual messaging happens via Supabase Realtime — the frontend subscribes "
        "to the returned channel_id for sub-millisecond message delivery."
    ),
)
async def init_dm(
    body: DMInitRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> DMInitResponse:
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    if str(body.recipient_id) == current_user_id:
        raise HTTPException(status_code=400, detail="You cannot DM yourself.")

    # Canonical ordering prevents duplicate DM channels (user A↔B == user B↔A)
    participants = sorted([current_user_id, str(body.recipient_id)])
    participant_key = f"dm:{participants[0]}:{participants[1]}"

    # Check if a DM channel already exists between these two users
    existing = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("channels")
            .select("id")
            .eq("kind", "dm")
            .eq("name", participant_key)
            .execute()
        ),
    )

    if existing.data:
        channel_id = existing.data[0]["id"]
        logger.info("[DM] Existing DM channel %s returned for %s <-> %s", channel_id, current_user_id, body.recipient_id)
        return DMInitResponse(channel_id=uuid_module.UUID(channel_id))

    # Create a new DM channel
    new_channel_id = str(uuid_module.uuid4())
    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("channels").insert({
                "id": new_channel_id,
                "hub_id": None,             # DMs are not hub-scoped
                "name": participant_key,    # Canonical unique key for this pair
                "kind": "dm",
                "description": f"Direct message channel",
            }).execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create DM channel: {e}")

    logger.info("[DM] Created DM channel %s for %s <-> %s", new_channel_id, current_user_id, body.recipient_id)
    return DMInitResponse(channel_id=uuid_module.UUID(new_channel_id))


# ─── GET /api/v1/hubs/{hub_id}/members ───────────────────────────────────────

@router.get(
    "/api/v1/hubs/{hub_id}/members",
    response_model=list[GroupMemberResponse],
    summary="List members of a hub/group",
    description="Returns all members of a hub with their profile info, ordered by join date.",
)
async def list_hub_members(hub_id: str):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("hub_members")
            .select("user_id, joined_at, profiles!hub_members_user_id_fkey(username, display_name, avatar_url, karma_score)")
            .eq("hub_id", hub_id)
            .order("joined_at", desc=False)
            .limit(50)
            .execute()
        ),
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

@router.get(
    "/api/v1/hubs/{hub_id}/leaderboard",
    response_model=list[LeaderboardEntry],
    summary="Group leaderboard by karma",
    description="Returns members sorted by karma score, top 10.",
)
async def hub_leaderboard(hub_id: str):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("hub_members")
            .select("user_id, profiles!hub_members_user_id_fkey(username, avatar_url, karma_score)")
            .eq("hub_id", hub_id)
            .limit(50)
            .execute()
        ),
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

    # Sort by karma descending and assign ranks
    entries.sort(key=lambda e: e["karma_score"], reverse=True)
    results = []
    for i, entry in enumerate(entries[:10]):
        results.append(LeaderboardEntry(rank=i + 1, **entry))
    return results

# ─── POST /api/v1/messages ───────────────────────────────────────────────────

@router.post(
    "/api/v1/messages",
    status_code=201,
    summary="Send a message to a channel",
)
async def send_message(
    body: SendMessageRequest,
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    message_id = str(uuid_module.uuid4())
    
    try:
        await loop.run_in_executor(
            None,
            lambda: sb.table("messages").insert({
                "id": message_id,
                "channel_id": body.channel_id,
                "user_id": current_user_id,
                "content": body.content,
                "is_hidden": False,
            }).execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {e}")
        
    return {"id": message_id, "status": "sent"}

# ─── GET /api/v1/channels/{channel_id}/messages ──────────────────────────────

@router.get(
    "/api/v1/channels/{channel_id}/messages",
    summary="Get messages for a channel",
)
async def get_messages(
    channel_id: str,
    limit: int = 100,
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    try:
        resp = await loop.run_in_executor(
            None,
            lambda: sb.table("messages")
                .select("id, channel_id, user_id, content, created_at, is_hidden, profiles!messages_user_id_fkey(username, avatar_url)")
                .eq("channel_id", channel_id)
                .eq("is_hidden", False)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
        )
        return resp.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {e}")


# ─── POST /api/v1/uploads/chat ───────────────────────────────────────────────

@router.post(
    "/api/v1/uploads/chat",
    summary="Upload a file for a chat message",
    status_code=201,
)
async def upload_chat_file(
    file: UploadFile = FastAPIFile(...),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    """Upload any file to Supabase storage using the service role key (bypasses RLS).
    Returns a public URL that can be embedded in a chat message payload."""
    sb = get_supabase()
    file_bytes = await file.read()
    safe_name = file.filename.replace(" ", "_") if file.filename else "file"
    file_key = f"chat/{current_user_id}/{uuid_module.uuid4()}_{safe_name}"

    try:
        sb.storage.from_("exports").upload(
            file_key,
            file_bytes,
            {"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {e}")

    public_url = sb.storage.from_("exports").get_public_url(file_key)
    return {"url": public_url, "key": file_key, "name": file.filename, "size": len(file_bytes)}
