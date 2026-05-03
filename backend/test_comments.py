import asyncio
import os
import sys

sys.path.append("/Users/likhith./Startup_Scope_AI")

from realtime_groups.backend.core.supabase_client import get_supabase

async def test_insert():
    sb = get_supabase()
    print("Testing insert into post_comments...")
    try:
        # We need a real post_id for the test to work due to foreign keys, or it will throw an FK error
        # Let's just catch the exception to see what it is
        resp = sb.table("post_comments").insert({
            "post_id": "00000000-0000-0000-0000-000000000000",
            "author_id": "00000000-0000-0000-0000-000000000000",
            "content": "test comment"
        }).execute()
        print(resp.data)
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_insert())
