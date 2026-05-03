import os
import asyncio
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    from dotenv import load_dotenv
    load_dotenv()
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

async def test():
    try:
        hubs_resp = sb.table("hubs").select("id, name, description, icon_url, member_count").order("member_count", desc=True).execute()
        hub_rows = hubs_resp.data or []
        print("HUBS:", len(hub_rows))
        
        hub_ids = [r["id"] for r in hub_rows]
        print("HUB IDS:", len(hub_ids))
        
        if hub_ids:
            channels_resp = sb.table("channels").select("hub_id").in_("hub_id", hub_ids).execute()
            print("CHANNELS:", len(channels_resp.data or []))
    except Exception as e:
        print("ERROR:", e)

asyncio.run(test())
