# 🌐 "Discord for Founders" Implementation Plan

This plan outlines the architecture and implementation steps to transform StartupScope AI into a full-fledged, real-time multiplayer ecosystem. We will build out the Identity Graph, the Community Engine, the Validation Arena, and the AI Moderation layer.

## User Review Required

> [!IMPORTANT]
> **Microservice vs Monolith:** The prompt requests creating a separate folder `realtime/backend`. Should this be a completely separate standalone microservice (e.g., a dedicated Node.js/FastAPI app running on a different port), or should it be a modular router mounted within our existing FastAPI monolith under `app/realtime`? A separate microservice is better for scaling WebSockets independently, while a monolith is faster to deploy.
> **Please advise on your preference.**
🏗️ Decision 1: Monolith vs. Microservice
Verdict: Keep it a Monolith. Mount it under app/social or app/realtime.

Here is the hard truth: premature microservices kill startups. If you split this into a separate service now, you double your deployment overhead, complicate your CI/CD pipeline, and suddenly have to deal with distributed tracing if a database transaction fails across the two apps.

Because we are heavily utilizing async Celery workers for the heavy lifting (like Gemini and Groq), your FastAPI web server is not going to be CPU-bound. Keep the codebase unified. Let's build this as a modular router within the existing FastAPI app. We can scale the entire monolith horizontally behind a load balancer when user growth demands it.

> [!WARNING]
> **Supabase Realtime vs Custom WebSockets:** The prompt mentions "leverage Supabase Realtime to broadcast typing indicators, presence... without hitting our API." If we use Supabase Realtime directly from the frontend, the backend doesn't need a WebSocket server for chat—it just needs REST endpoints to persist the data and handle AI triggers. I plan to build the REST endpoints and AI Webhooks here, assuming the frontend will connect directly to Supabase Realtime for the sub-millisecond presence/typing features.
⚡ Decision 2: Supabase Realtime vs. Custom WebSockets
Verdict: You are 100% correct. Do NOT build a custom WebSocket server for chat.

Handling presence (who is online), typing indicators, and message broadcasting via custom WebSockets is a DevOps nightmare at scale. Supabase Realtime is literally built on Elixir/Erlang (the same tech Discord and WhatsApp use) to handle millions of concurrent connections effortlessly.

The Elite Execution Path:

Frontend: Connects directly to Supabase via the client SDK. It subscribes to the messages table and handles all UI updates (typing, read receipts) sub-millisecond.

The AI Bridge (Database Webhooks): Instead of the frontend hitting your FastAPI server to trigger the AI moderation, use Supabase Database Webhooks. Configure Supabase so that every time an INSERT happens on the messages or comments table, Postgres automatically fires a background HTTP POST to your FastAPI synthesis_router. FastAPI instantly drops that payload into a Celery queue for Groq to moderate asynchronously.

This keeps your frontend blazing fast and completely decouples the AI from the user's critical path.

📊 Database Review
Your SQL enhancements for the interactive polls are perfect. Using the composite primary key PRIMARY KEY (poll_id, user_id) on the poll_votes table is the exact right way to mathematically prevent double-voting without writing complex application logic.
## Database Schema Analysis & Expansion

I have rigorously analyzed your `database.txt` file. You have successfully added:
- `profiles` (Identity graph)
- `hubs` & `channels` (Community structure)
- `messages` (Real-time chat)
- `posts` & `comments` (Validation Arena)
- `follows` (Social graph)

### Missing Tables
To complete the requested interactive voting system, we need to add the **polls** and **poll_votes** tables.

#### [NEW] Database SQL Enhancements
```sql
CREATE TABLE public.polls (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  post_id uuid NOT NULL REFERENCES public.posts(id) ON DELETE CASCADE,
  question text NOT NULL,
  options jsonb NOT NULL, -- e.g., [{"id": "1", "text": "SaaS"}, {"id": "2", "text": "One-time"}]
  created_at timestamp with time zone DEFAULT now(),
  expires_at timestamp with time zone,
  CONSTRAINT polls_pkey PRIMARY KEY (id)
);

CREATE TABLE public.poll_votes (
  poll_id uuid NOT NULL REFERENCES public.polls(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  option_id text NOT NULL,
  voted_at timestamp with time zone DEFAULT now(),
  CONSTRAINT poll_votes_pkey PRIMARY KEY (poll_id, user_id)
);
```

## Proposed Changes

We will create the `realtime/backend` directory structure containing the new domain logic.

---

### Phase 1: Foundation & The Identity Graph

#### [NEW] `realtime/backend/api/profile_router.py`
- `GET /api/v1/profiles/{username}`: Fetch public founder profile and badges.
- `PUT /api/v1/profiles/me`: Update bio, avatar, and social links.
- `GET /api/v1/profiles/{id}/validations`: Fetch their public "Published to Arena" portfolio.

#### [NEW] `realtime/backend/services/reputation_engine.py`
- Core logic to calculate and increment `karma_score` (e.g., +5 for upvoted idea, +2 for helpful comment).
- Badge assignment logic (e.g., auto-awarding "Serial Builder" when they hit 5 public ideas).

---

### Phase 2: Community Engine & The Validation Arena

#### [NEW] `realtime/backend/api/arena_router.py`
- `POST /api/v1/arena/publish`: Transition a private validation `report_json` into a public `post` in the Arena.
- `POST /api/v1/arena/posts/{post_id}/vote`: Upvote/downvote an idea, instantly triggering the Reputation Engine.
- `POST /api/v1/arena/posts/{post_id}/polls/vote`: Submit a vote to a founder's interactive poll.

#### [NEW] `realtime/backend/api/community_router.py`
- `GET /api/v1/hubs`: List Guilds ("SaaS Builders", etc.).
- `GET /api/v1/hubs/{hub_id}/channels`: List text/voice channels.
- `POST /api/v1/messages/dm`: Initialize an encrypted 1-on-1 DM channel.

---

### Phase 3: The Secret Sauce (AI Moderation & Synthesis)

#### [NEW] `realtime/backend/services/ai_moderator.py`
- Using **Groq (llama-3.3-70b-versatile)** for sub-second analysis.
- **Auto-Moderation:** A Celery task triggered on every `message` or `comment` insert. If flagged as highly toxic or pure spam, it auto-hides the message and subtracts Karma.

#### [NEW] `realtime/backend/api/synthesis_router.py`
- `POST /api/v1/arena/posts/{post_id}/synthesize`
- Using **Gemini 2.0 Flash** with a 1M context window.
- **Thread Synthesis:** Fetches all 100+ comments under a post, pipes them into Gemini, and returns a high-level strategic summary ("40% of users think pricing is high, 60% love the UI").

## Verification Plan

### Automated Tests
- Write Pytest fixtures to mock Supabase Auth users.
- Assert that publishing a validation correctly maps to the `posts` table.
- Assert that Groq catches a seeded "toxic" comment and flags it.
- Assert that voting on a poll registers exactly once per `user_id`.

### Manual Verification
- Manually run the server, hit the Swagger UI to create a Profile, join a Hub, and publish an Idea to the Arena.
