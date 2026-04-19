# dependencies.py
import uuid
import time
from fastapi import Header, HTTPException, status
from typing import Dict

# Simple in-memory storage for rate limiting (User ID -> Last Request Timestamp)
_last_request_time: Dict[str, float] = {}
RATE_LIMIT_SECONDS = 2 

async def rate_limit_user(
    x_user_id: str = Header(..., description="User ID (UUID) for the request")
) -> str:
    """
    Rate limiter / auth stub for testing phase.
    Extracts the user ID from the header, validates it is a well-formed UUID,
    and enforces a 10s cooldown per user.
    """
    try:
        uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-User-Id header must be a valid UUID."
        )

    # Basic Rate Limiting
    now = time.time()
    if x_user_id in _last_request_time:
        elapsed = now - _last_request_time[x_user_id]
        if elapsed < RATE_LIMIT_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Please wait {int(RATE_LIMIT_SECONDS - elapsed)}s."
            )
    
    _last_request_time[x_user_id] = now
    return x_user_id