# workspace_router.py
# ---------------------------------------------------------------------------
# FEATURE 14: Team Collaboration (Python-side)
#
# REST endpoints for workspace management:
#   POST /api/v1/workspaces          — Create a new workspace
#   GET  /api/v1/workspaces          — List user's workspaces
#   POST /api/v1/workspaces/{id}/invite — Invite a user by email
#   GET  /api/v1/workspaces/{id}/members — List workspace members
#
# DESIGN:
#   - Workspaces are stored in a `workspaces` table.
#   - Membership is stored in `workspace_members` (FK to workspaces + user_id).
#   - Invitations send an email via Supabase Auth admin's invite method.
#   - RLS is assumed to be handled in Supabase (as specified in the brief).
#   - The creator is automatically added as 'owner' role.
#
# SUPABASE TABLES REQUIRED:
#   CREATE TABLE workspaces (
#     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     name TEXT NOT NULL,
#     created_by UUID NOT NULL REFERENCES auth.users(id),
#     created_at TIMESTAMPTZ DEFAULT now()
#   );
#
#   CREATE TABLE workspace_members (
#     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
#     user_id UUID NOT NULL REFERENCES auth.users(id),
#     email TEXT NOT NULL,
#     role TEXT NOT NULL DEFAULT 'viewer',
#     invited_at TIMESTAMPTZ DEFAULT now(),
#     UNIQUE(workspace_id, user_id)
#   );
# ---------------------------------------------------------------------------

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field
from supabase import create_client, Client

from app.core.config import settings


router = APIRouter(prefix="/api/v1", tags=["Team Collaboration"])


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------
_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


# ---------------------------------------------------------------------------
# Auth helper — extract user_id from Supabase JWT
# ---------------------------------------------------------------------------

async def _get_user_id(authorization: str = Header(...)) -> str:
    """
    Extracts user_id from the Supabase JWT bearer token.

    The service-role client can verify any JWT issued by our Supabase project.
    In production, use a proper middleware. This is a lightweight version.
    """
    try:
        token = authorization.replace("Bearer ", "").strip()
        supabase = _get_supabase()
        user_response = supabase.auth.get_user(token)

        if user_response and user_response.user:
            return user_response.user.id

        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class CreateWorkspaceRequest(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Workspace name.",
    )


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    created_by: str
    created_at: Optional[str] = None
    member_count: int = 0


class InviteRequest(BaseModel):
    email: str = Field(
        ...,
        description="Email address of the user to invite.",
    )
    role: str = Field(
        default="viewer",
        description="Role: 'owner', 'editor', or 'viewer'.",
    )


class InviteResponse(BaseModel):
    message: str
    email: str
    role: str
    workspace_id: str


class MemberResponse(BaseModel):
    user_id: str
    email: str
    role: str
    invited_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/workspaces",
    response_model=WorkspaceResponse,
    summary="Create a new workspace",
    description="Feature 14: Creates a workspace and adds the creator as 'owner'.",
)
async def create_workspace(
    request: CreateWorkspaceRequest,
    authorization: str = Header(...),
) -> WorkspaceResponse:
    """
    POST /api/v1/workspaces

    Creates a new workspace and adds the authenticated user as 'owner'.
    """
    user_id = await _get_user_id(authorization)
    supabase = _get_supabase()

    try:
        # Create workspace
        ws_result = (
            supabase.table("workspaces")
            .insert({
                "name": request.name,
                "created_by": user_id,
            })
            .execute()
        )

        if not ws_result.data:
            raise HTTPException(status_code=500, detail="Failed to create workspace.")

        ws = ws_result.data[0]
        workspace_id = ws["id"]

        # Auto-add creator as owner
        supabase.table("workspace_members").insert({
            "workspace_id": workspace_id,
            "user_id": user_id,
            "email": "",  # Will be filled from auth context
            "role": "owner",
        }).execute()

        return WorkspaceResponse(
            id=workspace_id,
            name=ws.get("name", request.name),
            created_by=user_id,
            created_at=ws.get("created_at"),
            member_count=1,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Workspace] Create failed: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Workspace creation failed: {e}")


@router.get(
    "/workspaces",
    response_model=List[WorkspaceResponse],
    summary="List workspaces the user belongs to",
)
async def list_workspaces(
    authorization: str = Header(...),
) -> List[WorkspaceResponse]:
    """
    GET /api/v1/workspaces

    Returns all workspaces the authenticated user is a member of.
    """
    user_id = await _get_user_id(authorization)
    supabase = _get_supabase()

    try:
        # Find workspace IDs the user belongs to
        memberships = (
            supabase.table("workspace_members")
            .select("workspace_id")
            .eq("user_id", user_id)
            .execute()
        )

        if not memberships.data:
            return []

        ws_ids = [m["workspace_id"] for m in memberships.data]

        # Fetch workspace details
        workspaces = (
            supabase.table("workspaces")
            .select("id, name, created_by, created_at")
            .in_("id", ws_ids)
            .execute()
        )

        results = []
        for ws in (workspaces.data or []):
            # Count members
            count_result = (
                supabase.table("workspace_members")
                .select("id", count="exact")
                .eq("workspace_id", ws["id"])
                .execute()
            )
            member_count = count_result.count if hasattr(count_result, "count") and count_result.count else 0

            results.append(WorkspaceResponse(
                id=ws["id"],
                name=ws.get("name", ""),
                created_by=ws.get("created_by", ""),
                created_at=ws.get("created_at"),
                member_count=member_count,
            ))

        return results

    except Exception as e:
        print(f"[Workspace] List failed: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Failed to list workspaces: {e}")


@router.post(
    "/workspaces/{workspace_id}/invite",
    response_model=InviteResponse,
    summary="Invite a user to a workspace by email",
    description=(
        "Feature 14: Sends an invite email via Supabase Auth admin. "
        "If the user doesn't have an account, Supabase creates one "
        "and sends a magic link."
    ),
)
async def invite_member(
    workspace_id: str,
    request: InviteRequest,
    authorization: str = Header(...),
) -> InviteResponse:
    """
    POST /api/v1/workspaces/{workspace_id}/invite

    Invites a user by email. Uses Supabase Auth admin to send the invite.
    """
    user_id = await _get_user_id(authorization)
    supabase = _get_supabase()

    # Verify the inviter is an owner/editor of this workspace
    # BUG FIX: .single() raises an APIError when zero rows are found (not 'no auth'),
    # causing a 500 instead of the intended 403. Use .limit(1) + data check instead.
    membership = (
        supabase.table("workspace_members")
        .select("role")
        .eq("workspace_id", workspace_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if not membership.data:
        raise HTTPException(status_code=403, detail="You are not a member of this workspace.")

    inviter_role = membership.data[0].get("role", "viewer")
    if inviter_role not in ("owner", "editor"):
        raise HTTPException(
            status_code=403,
            detail=f"Your role '{inviter_role}' cannot invite members. Only 'owner' or 'editor' can."
        )

    # Validate the role being assigned
    valid_roles = ("owner", "editor", "viewer")
    if request.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{request.role}'. Must be one of: {valid_roles}",
        )

    # Only owners can invite other owners
    if request.role == "owner" and inviter_role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only workspace owners can assign the 'owner' role."
        )

    try:
        # Use Supabase Auth admin to invite the user by email.
        # This sends a magic link email. If the user already has an account,
        # they just get a notification.
        invite_result = supabase.auth.admin.invite_user_by_email(request.email)

        # Get the invited user's ID (may be new or existing)
        invited_user_id = None
        if invite_result and hasattr(invite_result, "user") and invite_result.user:
            invited_user_id = invite_result.user.id
        elif isinstance(invite_result, dict):
            invited_user_id = invite_result.get("user", {}).get("id")

        # Add to workspace_members — use upsert for idempotency
        # (re-inviting an existing member updates their role instead of erroring)
        if invited_user_id:
            supabase.table("workspace_members").upsert({
                "workspace_id": workspace_id,
                "user_id": invited_user_id,
                "email": request.email,
                "role": request.role,
            }, on_conflict="workspace_id,user_id").execute()

        return InviteResponse(
            message=f"Invitation sent to {request.email}.",
            email=request.email,
            role=request.role,
            workspace_id=workspace_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Workspace] Invite failed: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Invite failed: {str(e)[:200]}")


@router.get(
    "/workspaces/{workspace_id}/members",
    response_model=List[MemberResponse],
    summary="List members of a workspace",
)
async def list_members(
    workspace_id: str,
    authorization: str = Header(...),
) -> List[MemberResponse]:
    """
    GET /api/v1/workspaces/{workspace_id}/members

    Returns all members of the specified workspace.
    Requires the caller to be a member of the workspace.
    """
    user_id = await _get_user_id(authorization)
    supabase = _get_supabase()

    # Verify caller is a member
    membership = (
        supabase.table("workspace_members")
        .select("role")
        .eq("workspace_id", workspace_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not membership.data:
        raise HTTPException(status_code=403, detail="You are not a member of this workspace.")

    # Fetch all members
    members = (
        supabase.table("workspace_members")
        .select("user_id, email, role, invited_at")
        .eq("workspace_id", workspace_id)
        .execute()
    )

    return [
        MemberResponse(
            user_id=m["user_id"],
            email=m.get("email", ""),
            role=m.get("role", "viewer"),
            invited_at=m.get("invited_at"),
        )
        for m in (members.data or [])
    ]
