# realtime_groups/backend/schemas/social.py
# ---------------------------------------------------------------------------
# Pydantic v2 request/response models for the Discord-for-Founders module.
# These define the contract between the REST API and callers.
# ---------------------------------------------------------------------------

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Profile / Identity Graph
# ─────────────────────────────────────────────────────────────────────────────

class ProfileUpdateRequest(BaseModel):
    """PUT /api/v1/profiles/me — fields the founder wants to update."""
    display_name: Optional[str] = Field(None, max_length=64)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = Field(None, description="Public URL of the founder's avatar")
    twitter_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    website_url: Optional[str] = None


class ProfileResponse(BaseModel):
    """Public founder profile card returned by GET /api/v1/profiles/{username}."""
    id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    karma_score: int = 0
    badges: list[str] = Field(default_factory=list)
    twitter_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    website_url: Optional[str] = None
    created_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# Arena — Publishing & Voting
# ─────────────────────────────────────────────────────────────────────────────

class PublishRequest(BaseModel):
    """
    POST /api/v1/arena/publish
    Transitions a private validation report into a public Arena post.
    """
    validation_id: uuid.UUID = Field(..., description="UUID of the completed validation to publish")
    title: str = Field(..., max_length=200)
    tags: list[str] = Field(default_factory=list, description="e.g. ['SaaS', 'B2B', 'AI']")


class PublishResponse(BaseModel):
    post_id: uuid.UUID
    message: str = "Your idea has been published to the Validation Arena!"


class VoteRequest(BaseModel):
    """POST /api/v1/arena/posts/{post_id}/vote — upvote or downvote an Arena post."""
    direction: int = Field(..., description="Must be +1 (upvote) or -1 (downvote)")

    @field_validator("direction")
    @classmethod
    def must_be_valid_direction(cls, v: int) -> int:
        if v not in (1, -1):
            raise ValueError("direction must be +1 or -1")
        return v


class VoteResponse(BaseModel):
    post_id: uuid.UUID
    new_score: int
    message: str


class PollVoteRequest(BaseModel):
    """POST /api/v1/arena/posts/{post_id}/polls/vote — submit a poll vote."""
    poll_id: uuid.UUID
    option_id: str = Field(..., description="The 'id' field from the poll's options JSONB array")


class PollVoteResponse(BaseModel):
    poll_id: uuid.UUID
    option_id: str
    message: str = "Vote recorded."


class ArenaPostSummary(BaseModel):
    """Lightweight post card used in paginated list responses."""
    id: uuid.UUID
    title: str
    content: str = ""                         # idea description text
    author_id: Optional[str] = None
    author_username: str
    author_avatar: Optional[str] = None        # profile avatar_url
    karma_score: int
    upvote_count: int
    downvote_count: int
    comment_count: int
    tags: list[str]
    created_at: Optional[datetime] = None
    report_json: Optional[Any] = None          # full AI report for tabs + feasibility
    validation_id: Optional[uuid.UUID] = None  # link back to validation pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Community — Hubs, Channels, DMs
# ─────────────────────────────────────────────────────────────────────────────

class HubResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    icon_url: Optional[str] = None
    member_count: int = 0
    channel_count: int = 0


class ChannelResponse(BaseModel):
    id: uuid.UUID
    hub_id: Optional[uuid.UUID] = None   # None for DM channels (no hub association)
    name: str
    kind: str = Field(default="text", description="'text', 'voice', or 'dm'")
    description: Optional[str] = None


class DMInitRequest(BaseModel):
    """POST /api/v1/messages/dm — initialize a 1-on-1 DM channel."""
    recipient_id: uuid.UUID = Field(..., description="UUID of the founder to message")


class DMInitResponse(BaseModel):
    channel_id: uuid.UUID
    message: str = "DM channel ready. Connect via Supabase Realtime."


# ─────────────────────────────────────────────────────────────────────────────
# AI Synthesis
# ─────────────────────────────────────────────────────────────────────────────

class SynthesisResponse(BaseModel):
    """POST /api/v1/arena/posts/{post_id}/synthesize"""
    post_id: uuid.UUID
    summary: str = Field(..., description="Gemini 2.0 Flash strategic synthesis of all comments")
    comment_count: int
    key_themes: list[str] = Field(default_factory=list)
    sentiment_breakdown: dict[str, Any] = Field(
        default_factory=dict,
        description="e.g. {'positive': 60, 'negative': 40}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Payload (Supabase Database Webhook → Moderation)
# ─────────────────────────────────────────────────────────────────────────────

class SupabaseWebhookPayload(BaseModel):
    """
    Shape of the HTTP POST body that Supabase Database Webhooks send to our
    /api/v1/webhooks/moderation endpoint on every INSERT to messages/comments.
    """
    model_config = {"populate_by_name": True}

    type: str = Field(..., description="e.g. 'INSERT'")
    table: str = Field(..., description="e.g. 'messages' or 'comments'")
    schema_name: str = Field(default="public", alias="schema")
    record: dict[str, Any] = Field(..., description="The new row data")
    old_record: Optional[dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Search & Trending
# ─────────────────────────────────────────────────────────────────────────────

class SearchResultPost(BaseModel):
    """A post result from search."""
    id: uuid.UUID
    title: Optional[str] = None
    content: str
    author_username: str = "unknown"
    upvote_count: int = 0
    downvote_count: int = 0
    comment_count: int = 0
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class SearchResultProfile(BaseModel):
    """A profile result from search."""
    id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    karma_score: int = 0
    badges: list[str] = Field(default_factory=list)


class TrendingPostResponse(BaseModel):
    """Trending post for the right sidebar."""
    id: uuid.UUID
    title: Optional[str] = None
    author_username: str = "unknown"
    upvote_count: int = 0
    comment_count: int = 0
    created_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# DM / Messages
# ─────────────────────────────────────────────────────────────────────────────

class ConversationSummary(BaseModel):
    """Summary of a DM conversation for the conversations list."""
    channel_id: uuid.UUID
    participant_id: uuid.UUID
    participant_username: str = "unknown"
    participant_avatar: Optional[str] = None
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None


class SendMessageRequest(BaseModel):
    """POST /api/v1/messages/{channel_id}/send"""
    content: str = Field(..., min_length=1, max_length=4000)
    validation_id: Optional[uuid.UUID] = Field(
        None,
        description="Optional — links this message to an AI validation for inline LiveIdeaCard rendering",
    )


class MessageResponse(BaseModel):
    """A single message in a chat timeline."""
    id: uuid.UUID
    channel_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    validation_id: Optional[uuid.UUID] = None
    is_hidden: bool = False
    created_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# Comments
# ─────────────────────────────────────────────────────────────────────────────

class CommentCreateRequest(BaseModel):
    """POST /api/v1/arena/posts/{post_id}/comments"""
    content: str = Field(..., min_length=1, max_length=2000)


class CommentResponse(BaseModel):
    """A single comment on an Arena post."""
    id: uuid.UUID
    post_id: uuid.UUID
    author_id: uuid.UUID
    author_username: str = "unknown"
    author_avatar: Optional[str] = None
    content: str
    upvote_count: int = 0
    is_hidden: bool = False
    created_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# Group Members & Leaderboard
# ─────────────────────────────────────────────────────────────────────────────

class GroupMemberResponse(BaseModel):
    """A member of a hub/group."""
    user_id: uuid.UUID
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    karma_score: int = 0
    joined_at: Optional[datetime] = None


class LeaderboardEntry(BaseModel):
    """Leaderboard entry for a group, ranked by karma."""
    rank: int
    user_id: uuid.UUID
    username: str
    avatar_url: Optional[str] = None
    karma_score: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Follows
# ─────────────────────────────────────────────────────────────────────────────

class FollowResponse(BaseModel):
    """Response from follow/unfollow actions."""
    follower_id: uuid.UUID
    following_id: uuid.UUID
    message: str
