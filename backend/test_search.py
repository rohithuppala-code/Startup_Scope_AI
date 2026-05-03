import asyncio
import os
import sys

sys.path.append("/Users/likhith./Startup_Scope_AI")
from realtime_groups.backend.core.supabase_client import get_supabase

async def test_search():
    sb = get_supabase()
    search_pattern = "%a%"
    try:
        resp = sb.table("profiles").select("id, username, display_name, avatar_url, bio, karma_score, badges").or_(f"username.ilike.{search_pattern},display_name.ilike.{search_pattern}").execute()
        print("Success:", resp.data)
    except Exception as e:
        print("Exception:", e)

if __name__ == "__main__":
    asyncio.run(test_search())
