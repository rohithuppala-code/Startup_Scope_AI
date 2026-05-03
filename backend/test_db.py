import asyncio
from supabase import create_client
from app.core.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
resp = supabase.table("validations").select("id, status, error_message, updated_at").eq("id", "9b8d835d-a385-4736-85cb-b3572777f418").execute()
print(resp.data)
