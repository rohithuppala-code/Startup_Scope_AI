import asyncio
from datetime import datetime, timezone, timedelta
from supabase import create_client
from app.core.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
resp = supabase.table("validations").select("id, updated_at").eq("status", "processing").execute()
for row in resp.data:
    updated = datetime.fromisoformat(row['updated_at'].replace('Z', '+00:00'))
    if datetime.now(timezone.utc) - updated > timedelta(minutes=5):
        print(f"Fixing stuck validation: {row['id']}")
        supabase.table("validations").update({
            "status": "failed",
            "error_message": "Task orphaned due to worker restart."
        }).eq("id", row['id']).execute()
print("Done.")
