# Discord for Founders — `realtime_groups/backend`

The **Social Pillar** of StartupScope AI. A modular FastAPI sub-system that transforms the platform into a real-time multiplayer ecosystem for founders.

## Architecture Decision

> **Monolith-first.** All routers mount directly into the existing FastAPI app. No separate deployment. Scale horizontally behind a load balancer when growth demands it.

## Module Structure

```
realtime_groups/backend/
├── core/
│   ├── config.py           # Social-specific settings (reads same .env)
│   └── supabase_client.py  # Singleton Supabase service-role client
│
├── schemas/
│   └── social.py           # All Pydantic v2 request/response models
│
├── api/
│   ├── profile_router.py   # Phase 1: Identity Graph
│   ├── arena_router.py     # Phase 2: Validation Arena
│   ├── community_router.py # Phase 2: Hubs, Channels, DMs
│   └── synthesis_router.py # Phase 3: AI Synthesis + DB Webhook bridge
│
├── services/
│   ├── reputation_engine.py # Karma scoring + badge assignment
│   ├── ai_moderator.py      # Groq llama-3.3-70b moderation
│   └── synthesis_service.py # Gemini 2.0 Flash thread synthesis
│
├── workers/
│   ├── celery_app.py        # Celery instance (social queue)
│   └── celery_tasks.py      # moderate_content_task
│
├── tests/
│   └── test_social.py       # Pytest suite
│
├── social_app.py            # Mount point — include_social_routers(app)
└── database_schema.sql      # SQL to run in Supabase SQL Editor
```

## Integration (2 lines in `backend/app/main.py`)

```python
from realtime_groups.backend.social_app import include_social_routers
include_social_routers(app)
```

## Endpoints

### Phase 1: Identity Graph
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/profiles/{username}` | Public founder card + badges |
| `PUT` | `/api/v1/profiles/me` | Update own profile |
| `GET` | `/api/v1/profiles/{user_id}/validations` | Public Arena portfolio |

### Phase 2: Community Engine
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/hubs` | List all founder guilds |
| `GET` | `/api/v1/hubs/{hub_id}` | Hub detail |
| `GET` | `/api/v1/hubs/{hub_id}/channels` | List channels |
| `POST` | `/api/v1/hubs/{hub_id}/join` | Join a hub |
| `POST` | `/api/v1/messages/dm` | Init 1-on-1 DM channel |

### Phase 2: Validation Arena
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/arena/publish` | Publish validation to Arena |
| `GET` | `/api/v1/arena/posts` | Paginated feed (filter by tag, sort by score) |
| `GET` | `/api/v1/arena/posts/{post_id}` | Full post detail |
| `POST` | `/api/v1/arena/posts/{post_id}/vote` | Upvote / downvote |
| `POST` | `/api/v1/arena/posts/{post_id}/polls/vote` | Submit poll vote |

### Phase 3: AI Synthesis & Moderation
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/arena/posts/{post_id}/synthesize` | Gemini 2.0 Flash synthesis |
| `POST` | `/api/v1/webhooks/moderation` | Supabase DB Webhook → Celery |

## Realtime Architecture

```
Frontend ──► Supabase Realtime ──► Live messages/typing/presence (sub-ms)
                  │
              (DB INSERT)
                  │
         Supabase DB Webhook
                  │
                  ▼
     POST /api/v1/webhooks/moderation
                  │
             Celery Queue
                  │
         moderate_content_task
                  │
            Groq llama-3.3-70b
                  │
          (toxic?) ──► auto-hide + karma penalty
          (spam?)  ──► auto-hide
          (clean?) ──► no action
```

## Running the Social Worker

```bash
# From the backend/ directory
celery -A realtime_groups.backend.workers.celery_tasks worker \
    --loglevel=info -Q social --concurrency=4
```

## Database Setup

Run `database_schema.sql` in Supabase SQL Editor:
1. Go to Supabase Dashboard → SQL Editor
2. Paste and run the contents of `realtime_groups/backend/database_schema.sql`

## Supabase Webhook Configuration

1. Supabase Dashboard → Database → Webhooks → Create new webhook
2. Table: `messages`, Event: `INSERT`
3. URL: `https://your-api.com/api/v1/webhooks/moderation`
4. Repeat for `comments` table

## Running Tests

```bash
cd backend/
pytest ../realtime_groups/backend/tests/ -v
```
