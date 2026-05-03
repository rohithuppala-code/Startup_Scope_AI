# dependencies.py
import uuid
import time
from fastapi import Header, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Optional
from app.api.auth import _get_supabase

# Simple in-memory storage for rate limiting (User ID -> Last Request Timestamp)
_last_request_time: Dict[str, float] = {}
RATE_LIMIT_SECONDS = 2 

security = HTTPBearer(auto_error=False)

async def rate_limit_user(
    x_user_id: Optional[str] = Header(None, description="Fallback User ID (UUID) for the request"),
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """
    Rate limiter / auth stub.
    Extracts the user ID from the JWT token if present, falling back to x_user_id header.
    Validates it is a well-formed UUID and enforces a 2s cooldown per user.
    """
    user_id = None
    if auth and auth.credentials:
        try:
            supabase = _get_supabase()
            user_res = supabase.auth.get_user(auth.credentials)
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
        uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID must be a valid UUID."
        )

    # Basic Rate Limiting
    now = time.time()
    if user_id in _last_request_time:
        elapsed = now - _last_request_time[user_id]
        if elapsed < RATE_LIMIT_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Please wait {int(RATE_LIMIT_SECONDS - elapsed)}s."
            )
    
    _last_request_time[user_id] = now
    return user_id