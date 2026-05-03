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

try:
    resp = sb.rpc("get_channel_counts", {"p_hub_ids": ["00000000-0000-0000-0000-000000000000"]}).execute()
    print("SUCCESS", resp)
except Exception as e:
    print("ERROR:", e)
