from fastapi import APIRouter, HTTPException, status
from app.schemas.auth import LoginRequest, AuthResponse
from app.core.config import settings
from supabase import create_client, Client
from pydantic import BaseModel, Field
from typing import Optional
import uuid as uuid_module
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

# Service-role client for auth operations
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


class RegisterRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = Field(None, max_length=32)
    full_name: Optional[str] = Field(None, max_length=64)


def _ensure_profile(user_id: str, email: str, username: str | None = None, full_name: str | None = None):
    """
    Ensures a profiles row exists for the given auth user.
    If no username is provided, derives one from email.
    Handles unique constraint on username by appending a suffix.
    """
    base_username = (username or email.split("@")[0]).lower().replace(" ", "_")[:28]
    display = full_name or base_username

    # Check if profile already exists
    try:
        existing = supabase.table("profiles").select("id").eq("id", user_id).execute()
        if existing.data and len(existing.data) > 0:
            return  # Profile already exists, nothing to do
    except Exception:
        pass

    # Try inserting with the base username first
    for attempt in range(5):
        try_username = base_username if attempt == 0 else f"{base_username}_{str(uuid_module.uuid4())[:4]}"
        try:
            supabase.table("profiles").insert({
                "id": user_id,
                "username": try_username,
                "display_name": display,
                "full_name": display,
                "karma_score": 0,
                "badges": [],
            }).execute()
            logger.info("[Auth] Created profile for user=%s username=%s", user_id, try_username)
            return
        except Exception as e:
            err_str = str(e)
            if "duplicate" in err_str.lower() or "23505" in err_str:
                continue  # Username taken, try next
            else:
                logger.warning("[Auth] Profile insert failed: %s", err_str)
                return  # Other error, skip


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Authenticates a user with Supabase and ensures a profiles row exists.
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

        user_id = response.user.id
        _ensure_profile(user_id, request.email)

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


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(request: RegisterRequest):
    """
    Creates a new user in Supabase Auth and auto-creates their profile row.
    Accepts optional username and full_name.
    """
    try:
        response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password
        })

        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed. Email may already be in use."
            )

        user_id = response.user.id
        _ensure_profile(user_id, request.email, request.username, request.full_name)

        # If Supabase returns a session (email confirmation disabled), use it
        access_token = ""
        refresh_token = ""
        if response.session:
            access_token = response.session.access_token
            refresh_token = response.session.refresh_token

        return AuthResponse(
            user_id=user_id,
            email=response.user.email or request.email,
            access_token=access_token,
            refresh_token=refresh_token,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/ensure-profile")
async def ensure_profile_endpoint(request: LoginRequest):
    """
    Emergency endpoint: creates a profile row for an existing auth user.
    Call this if the user's profile is missing.
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        if not response.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        _ensure_profile(response.user.id, request.email)
        return {"message": "Profile ensured", "user_id": response.user.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/logout")
async def logout():
    """Invalidates a user session in Supabase."""
    try:
        supabase.auth.sign_out()
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Logout failed: {str(e)}"
        )
