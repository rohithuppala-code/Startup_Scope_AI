import asyncio
from app.core.config import settings
from supabase import create_client

sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
resp = sb.table("validations").select("id, status").eq("status", "pending").execute()
print(f"Pending Validations: {len(resp.data)}")
