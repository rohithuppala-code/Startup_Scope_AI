import asyncio
from supabase import create_client
from app.core.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
# get the channel id for the last file message
resp = supabase.table("messages").select("channel_id").ilike("content", "[FILE]%").order("created_at", desc=True).limit(1).execute()
if resp.data:
    channel_id = resp.data[0]['channel_id']
    count_resp = supabase.table("messages").select("id", count="exact").eq("channel_id", channel_id).execute()
    print(f"Total messages in channel {channel_id}: {count_resp.count}")
