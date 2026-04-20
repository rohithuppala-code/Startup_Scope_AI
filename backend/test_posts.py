import asyncio
from app.core.config import settings
from supabase import create_client

sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
resp = sb.table("posts").select("id, title, author_id, upvote_count, downvote_count, comment_count, tags, created_at, profiles!posts_author_id_fkey(username)").execute()
print(f"Arena Posts: {resp.data}")
