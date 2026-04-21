import uuid as uuid_module
import logging

logger = logging.getLogger(__name__)

def ensure_profile_exists(sb, current_user_id: str):
    try:
        existing = sb.table("profiles").select("id").eq("id", current_user_id).execute()
        if not existing.data or len(existing.data) == 0:
            username = f"user_{str(uuid_module.uuid4())[:6]}".lower()
            sb.table("profiles").insert({
                "id": current_user_id,
                "username": username,
                "display_name": username,
                "karma_score": 0,
                "badges": [],
            }).execute()
            logger.info(f"Auto-created profile for user {current_user_id}")
    except Exception as e:
        logger.error(f"Error ensuring profile exists: {e}")
