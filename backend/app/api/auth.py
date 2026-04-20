from fastapi import APIRouter, HTTPException, status
from app.schemas.auth import LoginRequest, AuthResponse
from app.core.config import settings
from supabase import create_client, Client

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# Service-role client for auth operations
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Authenticates a user with Supabase and returns session tokens.
    Also ensures a 'profiles' row exists (required by Arena FK constraints).
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        if not response.user or not response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # ── Ensure profiles row exists (Arena FK dependency) ──────────
        # posts, post_votes, hub_members, comments all FK to profiles(id).
        # If the user has never logged in before, they won't have a profiles
        # row, and every social operation would fail with a FK violation.
        user_id = response.user.id
        email_prefix = request.email.split("@")[0]
        try:
            supabase.table("profiles").upsert(
                {
                    "id": user_id,
                    "username": email_prefix,
                    "display_name": email_prefix,
                },
                on_conflict="id",
            ).execute()
        except Exception:
            pass  # Best-effort — profile may already exist

        return AuthResponse(
            user_id=user_id,
            email=response.user.email,
            access_token=response.session.access_token,
            refresh_token=response.session.refresh_token
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Login failed: {str(e)}"
        )

@router.post("/logout")
async def logout(access_token: str):
    """
    Invalidates a user session in Supabase.
    """
    try:
        # In Supabase, signOut uses the current session token
        supabase.auth.sign_out()
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Logout failed: {str(e)}"
        )
