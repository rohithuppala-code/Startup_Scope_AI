# realtime_groups/backend/api/dm_router.py
# ---------------------------------------------------------------------------
# DM & Messaging — Dedicated router for 1-on-1 Direct Messages
#
# GET  /api/v1/messages/conversations             — List all DM conversations
# POST /api/v1/messages/{channel_id}/send          — Send a message (REST)
# GET  /api/v1/messages/{channel_id}/history       — Paginated message history
# ---------------------------------------------------------------------------

import asyncio
import logging
import uuid as uuid_module
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from realtime_groups.backend.core.supabase_client import get_supabase
from realtime_groups.backend.schemas.social import (
    ConversationSummary,
    SendMessageRequest,
    MessageResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/messages", tags=["Direct Messages"])


async def get_current_user_id(
    x_user_id: Annotated[str, Header(description="Authenticated user UUID")]
) -> str:
    try:
        uuid_module.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="X-User-Id must be a valid UUID.")
    return x_user_id


# ─── GET /api/v1/messages/conversations ──────────────────────────────────────

@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
    summary="List all DM conversations",
    description=(
        "Returns all DM channels where the current user is a participant. "
        "DM channels use the naming pattern 'dm:uuid1:uuid2' with canonical ordering."
    ),
)
async def list_conversations(
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # DM channels have kind='dm' and name='dm:uuid1:uuid2'
    # The current user's ID appears somewhere in the name
    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("channels")
            .select("id, name, created_at")
            .eq("kind", "dm")
            .ilike("name", f"%{current_user_id}%")
            .execute()
        ),
    )

    conversations = []
    for ch in (resp.data or []):
        channel_id = ch["id"]
        name = ch.get("name", "")

        # Parse participant from 'dm:uuid1:uuid2' format
        parts = name.split(":")
        if len(parts) == 3:
            other_id = parts[2] if parts[1] == current_user_id else parts[1]
        else:
            continue

        # Fetch the other participant's profile
        profile_resp = await loop.run_in_executor(
            None,
            lambda oid=other_id: (
                sb.table("profiles")
                .select("id, username, avatar_url")
                .eq("id", oid)
                .single()
                .execute()
            ),
        )
        profile = profile_resp.data or {}

        # Fetch the last message in this channel
        last_msg_resp = await loop.run_in_executor(
            None,
            lambda cid=channel_id: (
                sb.table("messages")
                .select("content, created_at")
                .eq("channel_id", cid)
                .eq("is_hidden", False)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            ),
        )
        last_msg = (last_msg_resp.data or [{}])[0] if last_msg_resp.data else {}

        conversations.append(ConversationSummary(
            channel_id=uuid_module.UUID(channel_id),
            participant_id=uuid_module.UUID(other_id),
            participant_username=profile.get("username", "unknown"),
            participant_avatar=profile.get("avatar_url"),
            last_message=last_msg.get("content"),
            last_message_at=last_msg.get("created_at"),
        ))

    # Sort by most recent message first
    conversations.sort(
        key=lambda c: c.last_message_at or "",
        reverse=True,
    )
    return conversations


# ─── POST /api/v1/messages/dm ───────────────────────────────────────────────

from pydantic import BaseModel

class DMRequest(BaseModel):
    recipient_id: str

@router.post(
    "/dm",
    status_code=200,
    summary="Init or get a DM channel",
    description="Creates or returns the canonical DM channel between two users.",
)
async def init_dm_channel(
    body: DMRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Canonical ordering for DM name
    u1, u2 = sorted([current_user_id, body.recipient_id])
    channel_name = f"dm:{u1}:{u2}"

    # Check if exists
    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("channels")
            .select("id")
            .eq("kind", "dm")
            .eq("name", channel_name)
            .execute()
        ),
    )

    if resp.data:
        return {"channel_id": resp.data[0]["id"]}

    # Create new
    new_id = str(uuid_module.uuid4())
    await loop.run_in_executor(
        None,
        lambda: (
            sb.table("channels")
            .insert({
                "id": new_id,
                "kind": "dm",
                "name": channel_name,
                "hub_id": None,
                "created_by": current_user_id,
            })
            .execute()
        ),
    )
    return {"channel_id": new_id}


# ─── POST /api/v1/messages/{channel_id}/send ─────────────────────────────────

@router.post(
    "/{channel_id}/send",
    response_model=MessageResponse,
    status_code=201,
    summary="Send a message",
    description=(
        "Sends a message to a DM or group channel via REST. "
        "Optionally includes a validation_id to render a LiveIdeaCard inline."
    ),
)
async def send_message(
    channel_id: str,
    body: SendMessageRequest,
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()

    # Verify the channel exists
    try:
        ch_resp = await loop.run_in_executor(
            None,
            lambda: (
                sb.table("channels")
                .select("id, kind, name")
                .eq("id", channel_id)
                .single()
                .execute()
            ),
        )
    except Exception:
        raise HTTPException(status_code=404, detail="Channel not found.")

    if not ch_resp.data:
        raise HTTPException(status_code=404, detail="Channel not found.")

    # For DM channels, verify user is a participant
    ch_data = ch_resp.data
    if ch_data.get("kind") == "dm":
        if current_user_id not in (ch_data.get("name") or ""):
            raise HTTPException(status_code=403, detail="You are not a participant in this DM.")

    insert_data = {
        "channel_id": channel_id,
        "user_id": current_user_id,
        "content": body.content,
        "is_hidden": False,
    }
    # Include validation_id if provided (for Compute-as-a-Post)
    if body.validation_id:
        insert_data["validation_id"] = str(body.validation_id)

    try:
        msg_resp = await loop.run_in_executor(
            None,
            lambda: sb.table("messages").insert(insert_data).execute(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {e}")

    if not msg_resp.data:
        raise HTTPException(status_code=500, detail="Message insert returned no data.")

    row = msg_resp.data[0]
    logger.info("[DM] Message sent by %s in channel %s", current_user_id, channel_id)
    return MessageResponse(**row)


# ─── GET /api/v1/messages/{channel_id}/history ───────────────────────────────

@router.get(
    "/{channel_id}/history",
    response_model=list[MessageResponse],
    summary="Get message history",
    description="Paginated message history for a DM or group channel. Ordered oldest-first.",
)
async def message_history(
    channel_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user_id: str = Depends(get_current_user_id),
):
    sb = get_supabase()
    loop = asyncio.get_running_loop()
    offset = (page - 1) * page_size

    resp = await loop.run_in_executor(
        None,
        lambda: (
            sb.table("messages")
            .select("id, channel_id, user_id, content, validation_id, is_hidden, created_at")
            .eq("channel_id", channel_id)
            .eq("is_hidden", False)
            .order("created_at", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        ),
    )

    return [MessageResponse(**row) for row in (resp.data or [])]
