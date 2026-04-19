# StartupScope AI Backend Endpoint Analysis

This document provides a rigorous architectural analysis of the StartupScope AI backend, breaking down exactly what every REST and WebSocket endpoint does, how they interact with external services (Celery, Redis, Supabase, Gemini), and the underlying data flow.

## 1. Core Validation Engine (`app/main.py`)

### `POST /api/v1/validate`
* **Purpose:** The entry point for validating a new startup idea.
* **Mechanism:** 
  1. Accepts the idea payload and generates a SHA-256 `idea_hash` and idempotency key.
  2. Performs an **anchor write** to the Supabase `validations` table marking the status as `pending`.
  3. Dispatches a message to the RabbitMQ broker for the Celery `process_validation` task.
  4. Returns an instant `202 Accepted` response with the newly generated `validation_id`.
* **Resilience:** If the message broker is down, it catches the dispatch error, marks the DB row as `failed`, and returns a `503 Service Unavailable` so clients know to retry.

### `GET /api/v1/validate/{validation_id}`
* **Purpose:** Fallback Cache-Aside read path for retrieving a completed validation report.
* **Mechanism:**
  1. Checks Redis cache (`validation:result:{validation_id}`) for an instant $O(1)$ response.
  2. On a cache miss, fetches the authoritative payload directly from the Supabase database.
  3. If the DB row is in a terminal state (`completed` or `failed`), it back-fills the Redis cache with a 24-hour TTL to speed up subsequent reads.
  4. Applies security bounds by ensuring the `user_id` requesting the read matches the owner of the validation row.

## 2. Real-Time Streaming (`app/api/ws_router.py`)

### `WebSocket /ws/validation/{validation_id}`
* **Purpose:** Provides a seamless real-time stream of the background AI processing to the frontend UI.
* **Mechanism:** 
  * The frontend establishes a persistent connection immediately after receiving a `validation_id`.
  * The server uses a global `ConnectionManager` that listens to a Redis Pub/Sub channel.
  * As the Celery worker reaches milestones (e.g., fetching competitor traffic, generating RAG chunks, synthesizing Groq consensus), it broadcasts JSON events to Redis.
  * This endpoint consumes those events and pushes them directly down the WebSocket, keeping the client UI beautifully animated and informed without expensive HTTP polling.

## 3. Conversational RAG (`app/api/chat_router.py`)

### `POST /api/v1/chat/{validation_id}`
* **Purpose:** Feature 12 ("Ask Your Report"). A stateless endpoint that allows users to ask specific follow-up questions about their generated validation.
* **Mechanism:**
  1. Verifies the report status is actually `completed`.
  2. Sends the user's question to Gemini to generate a `768-dimension` text embedding.
  3. Queries the Supabase pgvector `rag_chunks` table using cosine similarity to find the top 5 most relevant competitor data blocks.
  4. Injects the raw JSON report data + the 5 RAG chunks + recent chat history into a strict, structured prompt.
  5. Gemini `2.0-flash` returns a conversationally accurate answer grounded strictly in actual data, avoiding hallucination, complete with source text excerpts.

## 4. Idea Comparison Engine (`app/api/comparison_router.py`)

### `POST /api/v1/compare`
* **Purpose:** Feature 15. Pits multiple validated startup ideas against each other to help founders prioritize.
* **Mechanism:**
  1. Accepts an array of 2 to 10 `validation_ids`.
  2. Performs a bulk fetch from Supabase to pull down the completed JSON reports for all requested ideas.
  3. Feeds these reports into Gemini with instructions to act as a harsh VC judge.
  4. Returns a highly structured `ComparisonReport` that assigns comparative scores across dimensions (Market Size, Technical Difficulty, Capital Efficiency, Competitive Density), determines a definitive winner for each dimension, and provides a strategic narrative/recommendation.

## 5. Export Services (`app/api/export_router.py`)

### `GET /api/v1/export/{validation_id}/pdf`
* **Purpose:** Feature 13. Converts the validation markdown report into a premium, downloadable PDF.
* **Mechanism:**
  1. Fetches the Markdown representation of the validation report from the DB.
  2. Uses `WeasyPrint` to render it into a beautifully styled, dark-mode PDF document.
  3. Uploads the generated raw bytes to an active Supabase Storage bucket.
  4. Generates and returns a signed download URL valid for 1 hour.

## 6. Team Collaboration (`app/api/workspace_router.py`)

### `POST /api/v1/workspaces`
* **Purpose:** Initializes a collaborative workspace folder.
* **Mechanism:** Creates an entry in the Supabase `workspaces` table and instantly adds the creator to the `workspace_members` table with the `owner` role.

### `GET /api/v1/workspaces`
* **Purpose:** Returns all workspaces the currently authenticated user is part of.
* **Mechanism:** Joins the `workspace_members` table with `workspaces` to return metadata, including dynamic `member_count` aggregations.

### `POST /api/v1/workspaces/{workspace_id}/invite`
* **Purpose:** Invites new collaborators to a workspace.
* **Mechanism:** 
  1. Verifies the caller's role is `owner` or `editor`.
  2. Calls the Supabase Auth Admin API (`invite_user_by_email`). If the user exists, they get notified; if not, an account is created and a magic link is emailed.
  3. Adds the newly invited user's UUID into `workspace_members` with their assigned role (`editor` or `viewer`).

### `GET /api/v1/workspaces/{workspace_id}/members`
* **Purpose:** Lists everyone inside a specific workspace.
* **Mechanism:** Enforces membership access checks before returning the emails, UUIDs, and specific roles of every user in the target workspace.

## 7. Authentication (`app/api/auth.py`)

### `POST /api/v1/auth/login`
* **Purpose:** Validates user credentials natively.
* **Mechanism:** Passes the email and password directly to the Supabase GoTrue Auth service, returning the secure `access_token` (JWT) and `refresh_token` for subsequent restricted endpoint access.

### `POST /api/v1/auth/logout`
* **Purpose:** Terminates a user session.
* **Mechanism:** Discards the active token on the Supabase backend to prevent unauthorized lingering sessions.
