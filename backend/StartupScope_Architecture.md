# 🚀 StartupScope AI: System Architecture & Codebase Source of Truth

Welcome to the **StartupScope AI** backend documentation. This document serves as the absolute source of truth. It details the entire event-driven, real-time validation platform and **embeds the complete, currently-updated codebase** so you can see exactly how the live Gemini AI and WebSockets interact.

---

## 🏗️ 1. Architecture Overview (The "Anchor & Handoff" Flow)

StartupScope AI leverages an **asynchronous, event-driven architecture**.

1. **User Request (FastAPI):** User submits a startup idea to `POST /validate`.
2. **Anchor Write:** FastAPI instantly writes the idea to **Supabase** with a `pending` status.
3. **The Handoff:** FastAPI queues the heavy lifting to **RabbitMQ** (via Celery).
4. **Fast Response:** The user receives a `202 Accepted` instantly.
5. **Worker Execution (Celery):** A background worker locks via **Redis**, deduplicates, and runs the live AI pipeline (Firecrawl SDK + Gemini 1.5 Pro).
6. **Write-Through:** The worker saves the completed AI JSON report to Supabase.
7. **Real-time Trigger:** The worker publishes a JSON message to a **Redis Pub/Sub** channel (`validation_events`).
8. **Live WebSockets:** The FastAPI server listens to this Redis channel and pushes the completed data instantly to the connected browser.

---

## 💻 2. Complete Live Codebase By Component

### `app/core/config.py`
**Purpose:** Loads environment variables securely. We recently swapped OpenAI for `GEMINI_API_KEY`.
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    FIRECRAWL_API_KEY: str
    GEMINI_API_KEY: str
    REDIS_URL: str = "redis://localhost:6380/0"
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5673/"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
```

### `app/schemas/validation.py`
**Purpose:** Strict data validation.
```python
from pydantic import BaseModel, Field
from typing import Optional
import uuid

class ValidationRequest(BaseModel):
    idea_description: str = Field(..., min_length=10)
    target_market: Optional[str] = Field(None)
    budget_constraints: Optional[str] = Field(None)
    idempotency_key: Optional[str] = Field(None)

class ValidationResponse(BaseModel):
    validation_id: uuid.UUID
    status: str
    message: str
```

### `app/api/dependencies.py`
**Purpose:** Authentication and Rate Limits. (Currently disabled for unlimited development testing).
```python
from fastapi import Header

async def rate_limit_user(x_user_id: str = Header(..., description="User ID (UUID) for the request")) -> str:
    # DEVELOPMENT MODE: Unlimited requests allowed. Bypass applied.
    return x_user_id
```

### `app/services/ai_pipeline.py` (The Intelligence Layer)
**Purpose:** Live integration with Google Gemini and Firecrawl APIs. Output structured JSON.
```python
import json
from typing import Dict, Any, Tuple
from firecrawl import FirecrawlApp
import google.generativeai as genai
from app.core.config import settings

def firecrawl_scrape(idea_description: str) -> str:
    try:
        app = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
        search_query = f"competitors alternatives to {idea_description[:100]}"
        response = app.search(query=search_query, page_options={"fetchPageContent": True})
        
        markdown_results = []
        for result in response.get("data", []):
            if "markdown" in result:
                markdown_results.append(f"Source: {result.get('url')}\n{result['markdown'][:2500]}")
        
        if not markdown_results: return "No competitor data found."
        return "\n\n---\n\n".join(markdown_results)
    except Exception as e:
        return "Firecrawl search failed or timed out."

def generate_ai_report(idea_description: str, competitor_data: str) -> Tuple[Dict[str, Any], str, int, float]:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    
    system_prompt = """
    You are an elite Startup Analyst. Analyze the provided startup idea and competitor data.
    You MUST output valid JSON matching this exact structure:
    {
      "report": {"feasibility_score": integer, "market_viability": string, "gaps_identified": [string], "recommended_approach": string},
      "markdown": "A comprehensive markdown string..."
    }
    """
    user_prompt = f"Startup Idea: {idea_description}\n\nLive Competitor Data:\n{competitor_data}"
    
    model = genai.GenerativeModel(
        model_name="gemini-1.5-pro",
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json", "temperature": 0.7}
    )
    
    response = model.generate_content(user_prompt)
    parsed_response = json.loads(response.text)
    
    report_json = parsed_response.get("report", {})
    markdown_report = parsed_response.get("markdown", "")
    
    prompt_tokens = response.usage_metadata.prompt_token_count if hasattr(response, "usage_metadata") else 0
    completion_tokens = response.usage_metadata.candidates_token_count if hasattr(response, "usage_metadata") else 0
    total_tokens = prompt_tokens + completion_tokens
    estimated_cost = (prompt_tokens * 0.00000125) + (completion_tokens * 0.000005)
    
    return report_json, markdown_report, total_tokens, estimated_cost
```

### `app/worker/celery_tasks.py` (The Heavy Lifter)
**Purpose:** Asynchronous background job that prevents blocking Web traffic.
```python
import json
from datetime import datetime, timezone
import redis
from celery import Celery
from celery.exceptions import Retry
from supabase import create_client, Client
from app.core.config import settings
from app.services.ai_pipeline import firecrawl_scrape, generate_ai_report

celery_app = Celery("startupscope_worker", broker=settings.CELERY_BROKER_URL)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", enable_utc=True)
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

@celery_app.task(bind=True, name="app.worker.celery_tasks.process_validation", max_retries=3)
def process_validation(self, validation_id: str, idea_hash: str):
    lock_key = f"lock:validation:{validation_id}"
    lock = redis_client.lock(lock_key, timeout=300, blocking_timeout=5)
    
    try:
        if not lock.acquire(blocking=False): return {"status": "skipped"}
            
        try:
            # 1. Deduplication Cache
            duplicate = supabase.table("validations").select("*").eq("idea_hash", idea_hash).eq("status", "completed").limit(1).execute()
            if duplicate.data:
                dup_data = duplicate.data[0]
                supabase.table("validations").update({"status": "completed", "report_json": dup_data.get("report_json"), "markdown_report": dup_data.get("markdown_report")}).eq("id", validation_id).execute()
                redis_client.publish("validation_events", json.dumps({"validation_id": validation_id, "status": "completed"}))
                return {"status": "completed"}
                
            # 2. State to Processing
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("validations").update({"status": "processing", "processing_started_at": now_iso}).eq("id", validation_id).execute()
            
            row = supabase.table("validations").select("idea_description").eq("id", validation_id).single().execute()
            
            # 3. AI Pipeline
            competitor_data = firecrawl_scrape(row.data.get("idea_description"))
            report, markdown, tokens, cost = generate_ai_report(row.data.get("idea_description"), competitor_data)
            
            # 4. Write-through Cache & Complete
            supabase.table("validations").update({
                "status": "completed", "report_json": report, "markdown_report": markdown, 
                "tokens_used": tokens, "estimated_cost": cost, "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", validation_id).execute()
            
            redis_client.publish("validation_events", json.dumps({"validation_id": validation_id, "status": "completed"}))
            return {"status": "completed"}
            
        except Retry:
            raise
        except Exception as e:
            supabase.table("validations").update({"status": "failed", "error_message": str(e)}).eq("id", validation_id).execute()
            redis_client.publish("validation_events", json.dumps({"validation_id": validation_id, "status": "failed"}))
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
            
    finally:
        if lock.owned(): lock.release()
```

### `app/websockets/manager.py` & `app/websockets/redis_listener.py`
**Purpose:** Real-time push logic mapped directly to the `validation_events` Redis channel. Connections map `validation_id` -> WebSocket.

### `app/main.py`
**Purpose:** The central router containing the main REST API and WebSocket injections.
```python
import hashlib, uuid, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Depends
from app.core.config import settings
from app.schemas.validation import ValidationRequest, ValidationResponse
from app.websockets.manager import manager
from app.websockets.redis_listener import listen_to_redis
from app.api.ws_router import router as ws_router
from app.api.dependencies import rate_limit_user
from supabase import create_client, Client
from celery import Celery

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
celery_app = Celery("startupscope_worker", broker=settings.CELERY_BROKER_URL)

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_task = asyncio.create_task(listen_to_redis(manager))
    yield
    redis_task.cancel()
    try: await redis_task
    except asyncio.CancelledError: pass

app = FastAPI(title="StartupScope AI", lifespan=lifespan)
app.include_router(ws_router)

@app.post("/api/v1/validate", response_model=ValidationResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_validation(request: ValidationRequest, x_user_id: str = Depends(rate_limit_user)):
    id_key = request.idempotency_key or str(uuid.uuid4())
    idea_hash = hashlib.sha256(request.idea_description.encode("utf-8")).hexdigest()
    
    try:
        res = supabase.table("validations").insert({
            "user_id": x_user_id, "idea_description": request.idea_description,
            "target_market": request.target_market, "budget_constraints": request.budget_constraints,
            "status": "pending", "idempotency_key": id_key, "idea_hash": idea_hash
        }).execute()
        v_id = res.data[0]["id"]
    except Exception as e:
        if "unique constraint" in str(e).lower():
            raise HTTPException(status_code=409, detail="Duplicate idempotency key.")
        raise HTTPException(status_code=500, detail=str(e))
        
    celery_app.send_task("app.worker.celery_tasks.process_validation", kwargs={"validation_id": v_id, "idea_hash": idea_hash})
    
    return ValidationResponse(validation_id=uuid.UUID(v_id), status="pending", message="Task queued.")
```

---

## 🌐 3. Endpoints Documentation

### REST Endpoint
#### `POST /api/v1/validate`
- **Purpose:** Anchors data to Supabase and Hands off to RabbitMQ.
- **Headers:** `x-user-id` (UUID from auth.users). Rate limiter currently bypassed.

### WebSocket Endpoint
#### `WS /ws/validation/{validation_id}`
- **Purpose:** Receives live JSON push `{ "validation_id": "...", "status": "completed" }` the second Celery finishes.

---

## 🚀 4. How to Run It
```bash
./startup.sh
```
This single bash script handles Docker Compose (Redis, RabbitMQ, Postgres), boots the background Celery worker, and runs Uvicorn (FastAPI) in the foreground!
