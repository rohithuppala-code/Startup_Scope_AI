# Arena Restructure: Compute-Driven Social Network

Discarding the old Discord-clone layout (Hub Rail + Channel Panel). Replacing it with a LinkedIn/Twitter-style 3-column responsive grid where the center view dynamically swaps between Global Feed, Messages/Groups, Search, and Profile.

## Backend Endpoint Gap Analysis

> [!IMPORTANT]
> **Rigorous audit of what exists vs. what the new frontend requires.**

### ✅ Existing Endpoints (fully usable as-is)

| Endpoint | Router | Purpose |
|---|---|---|
| `GET /api/v1/arena/posts` | arena_router | Paginated feed (page, page_size, tag, sort_by) |
| `GET /api/v1/arena/posts/{post_id}` | arena_router | Single post detail w/ author profile join |
| `POST /api/v1/arena/publish` | arena_router | Publish validation → Arena post |
| `POST /api/v1/arena/posts/{post_id}/vote` | arena_router | Upvote/downvote |
| `POST /api/v1/arena/posts/{post_id}/polls/vote` | arena_router | Poll vote |
| `POST /api/v1/arena/posts/{post_id}/synthesize` | synthesis_router | AI thread synthesis |
| `GET /api/v1/profiles/{username}` | profile_router | Public founder card |
| `PUT /api/v1/profiles/me` | profile_router | Update own profile |
| `GET /api/v1/profiles/{user_id}/validations` | profile_router | User's published Arena posts |
| `GET /api/v1/hubs` | community_router | List all hubs (→ becomes "Groups") |
| `GET /api/v1/hubs/{hub_id}` | community_router | Group detail |
| `GET /api/v1/hubs/{hub_id}/channels` | community_router | Channels within a group |
| `POST /api/v1/hubs/{hub_id}/join` | community_router | Join a group |
| `POST /api/v1/messages/dm` | community_router | Initialize a 1-on-1 DM channel |
| `POST /api/v1/validate` | main.py | Submit idea → Celery pipeline |
| `GET /api/v1/validate/{id}` | main.py | Cache-aside read for validation status |
| `POST /api/v1/webhooks/moderation` | synthesis_router | Auto-moderation webhook |

### 🔴 Missing Endpoints — MUST ADD

| # | Endpoint | Purpose | Priority |
|---|---|---|---|
| 1 | `GET /api/v1/arena/search` | Search posts by keyword/tag, search profiles by username | **P0** |
| 2 | `GET /api/v1/messages/conversations` | List all DM conversations for current user (needed for Messages sidebar) | **P0** |
| 3 | `GET /api/v1/messages/{channel_id}/history` | Paginated message history for a DM/channel (the frontend currently does this via Supabase direct, but we need a REST fallback) | **P1** |
| 4 | `POST /api/v1/messages/{channel_id}/send` | Send a message via REST (for AI idea-share messages that need validation trigger) | **P0** |
| 5 | `GET /api/v1/arena/trending` | Trending ideas for the right sidebar (top voted in last 7 days) | **P1** |
| 6 | `GET /api/v1/profiles/suggested` | Suggested founders to follow (for right sidebar) | **P1** |
| 7 | `POST /api/v1/follows/{user_id}` | Follow a founder | **P1** |
| 8 | `DELETE /api/v1/follows/{user_id}` | Unfollow a founder | **P1** |
| 9 | `GET /api/v1/follows/following` | List users the current user follows | **P2** |
| 10 | `GET /api/v1/hubs/{hub_id}/members` | List group members (for right sidebar) | **P1** |
| 11 | `GET /api/v1/hubs/{hub_id}/leaderboard` | Group leaderboard by karma (for right sidebar) | **P2** |
| 12 | `POST /api/v1/arena/posts/{post_id}/comments` | Post a comment on an Arena post | **P0** |
| 13 | `GET /api/v1/arena/posts/{post_id}/comments` | List comments on a post | **P0** |

---

## Proposed Changes

### Backend — New Endpoints

#### [NEW] [search_router.py](file:///Users/likhith./Startup_Scope_AI/realtime_groups/backend/api/search_router.py)

New router for the `/arena/explore` view:
- `GET /api/v1/arena/search?q=...&type=posts|profiles` — Full-text search on `posts.title`, `posts.content`, and `profiles.username`/`profiles.display_name`
- `GET /api/v1/arena/trending` — Top 10 posts by upvote_count in the last 7 days
- `GET /api/v1/profiles/suggested` — Profiles with highest karma excluding self, limited to 5

#### [NEW] [dm_router.py](file:///Users/likhith./Startup_Scope_AI/realtime_groups/backend/api/dm_router.py)

New dedicated DM router (extracting DM-specific logic from community_router):
- `GET /api/v1/messages/conversations` — All DM channels where current user is a participant (parses `dm:uuid1:uuid2` name pattern)
- `POST /api/v1/messages/{channel_id}/send` — Send a message via REST, with optional `validation_id` field that triggers "Compute-as-a-Post" (kicks off AI validation and links it to the message)
- `GET /api/v1/messages/{channel_id}/history?page=1&page_size=50` — Paginated message history

#### [NEW] [comments_router.py](file:///Users/likhith./Startup_Scope_AI/realtime_groups/backend/api/comments_router.py)

Comments on Arena posts:
- `POST /api/v1/arena/posts/{post_id}/comments` — Create a comment (with moderation webhook trigger)
- `GET /api/v1/arena/posts/{post_id}/comments?page=1` — Paginated comment list with author join

#### [MODIFY] [community_router.py](file:///Users/likhith./Startup_Scope_AI/realtime_groups/backend/api/community_router.py)

Add group member endpoints:
- `GET /api/v1/hubs/{hub_id}/members` — List members with profile join (username, avatar, karma)
- `GET /api/v1/hubs/{hub_id}/leaderboard` — Members sorted by karma descending

#### [MODIFY] [social_app.py](file:///Users/likhith./Startup_Scope_AI/realtime_groups/backend/social_app.py)

Register the 3 new routers (search, dm, comments).

#### [MODIFY] [social.py (schemas)](file:///Users/likhith./Startup_Scope_AI/realtime_groups/backend/schemas/social.py)

Add Pydantic models for:
- `SearchResultResponse`, `TrendingPostResponse`
- `ConversationSummary`, `SendMessageRequest`, `MessageResponse`
- `CommentCreateRequest`, `CommentResponse`
- `GroupMemberResponse`, `LeaderboardEntry`
- `FollowResponse`

---

### Frontend — Complete File Manifest

#### Layout Shell

#### [MODIFY] [layout.tsx](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/layout.tsx)

**Complete rewrite** — From Discord 3-pane (Hub Rail + Channel Panel + Content) → LinkedIn-style 3-column:
- **Left Column (240px, collapsible)**: Vertical icon-heavy nav with links: Home (Feed), Search/Explore, Messages, My Groups, My Profile. Shows user avatar + karma at bottom.
- **Center Column (flex-1)**: Dynamic content area via `{children}`
- **Right Column (300px, hidden < lg)**: Context-aware sidebar — component slot that changes based on current route

#### Global Feed

#### [MODIFY] [page.tsx](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/page.tsx)

**Complete rewrite** — New feed with:
- **Composer** at top: glassmorphic input "What are you building?", "Attach Poll" button, "🚀 Run AI Validation" button
- **Infinite scroll** feed of `LiveIdeaCard` components
- Composer triggers `POST /api/v1/validate` then `POST /api/v1/arena/publish` once completed

#### LiveIdeaCard

#### [NEW] [LiveIdeaCard.tsx](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/components/LiveIdeaCard.tsx)

The core "Compute-as-a-Post" component. State machine:

```
COMPOSING → SUBMITTING → STREAMING → COMPLETED → INTERACTIVE
```

- **SUBMITTING**: Shows "Submitting idea..." with spinner
- **STREAMING**: Connects to `ws://...ws/validation/{id}`, shows progressive sections via framer-motion: "Firecrawling competitors...", "Running Gemini Consensus...", "Analyzing pricing..."
- **COMPLETED**: Transforms into rich interactive card with:
  - Feasibility score badge (color-coded)
  - Expandable tabs: Pricing / Competitors / Market Analysis
  - Upvote/Downvote buttons
  - Poll widget (if attached)
  - Comment count + "AI Synthesis" button

#### Messages (DMs)

#### [NEW] [page.tsx (messages)](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/messages/page.tsx)

- Left panel: conversation list from `GET /api/v1/messages/conversations`
- Right panel: `ChatTimeline` component for the selected conversation

#### ChatTimeline

#### [NEW] [ChatTimeline.tsx](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/components/ChatTimeline.tsx)

Real-time chat interface:
- Subscribes to Supabase Realtime on `messages` table filtered by `channel_id`
- Renders text messages AND `LiveIdeaCard` components inline (if message has `validation_id`)
- **Chat Composer** at bottom with "+" action menu:
  - "Share Idea (Run AI)" — opens composer overlay that triggers validation
  - "Create Poll" — inline poll creation
  - "Upload Pitch Deck" — file upload placeholder

#### Groups

#### [NEW] [page.tsx (groups)](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/groups/page.tsx)

- Grid of group cards from `GET /api/v1/hubs`
- Each card shows: name, description, member count, "Join" button
- Click → opens group detail with channel chat

#### [NEW] [page.tsx (group detail)](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/groups/[hubId]/page.tsx)

- Channel list sidebar
- Main chat area using `ChatTimeline` for selected channel
- Right sidebar shows group members + leaderboard

#### Search & Discover

#### [NEW] [page.tsx (explore)](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/explore/page.tsx)

- Prominent search bar hitting `GET /api/v1/arena/search`
- Toggle: "Ideas" | "Founders"
- Results rendered as `LiveIdeaCard` (for ideas) or `FounderCard` (for profiles)

#### Profile

#### [NEW] [page.tsx (profile)](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/profile/page.tsx)

User's own profile page — shows profile card, karma, badges, published ideas.

#### Right Sidebar Components

#### [NEW] [RightSidebar.tsx](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/components/RightSidebar.tsx)

Context-aware component that reads the current route and renders:
- **On Feed (`/arena`)**: TrendingIdeas + SuggestedFounders
- **In Group (`/arena/groups/[id]`)**: GroupMembers + GroupLeaderboard
- **In Messages**: Quick contact list

#### Shared Components

#### [NEW] [FounderCard.tsx](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/components/FounderCard.tsx)

Mini profile card used in search results, suggested founders, group members.

#### [NEW] [PollWidget.tsx](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/components/PollWidget.tsx)

Inline poll component: options, vote counts, progress bars, already-voted state.

#### [NEW] [StreamingProgress.tsx](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/(arena)/arena/components/StreamingProgress.tsx)

Animated progress indicator for the AI validation pipeline stages.

---

### Hooks & Stores

#### [MODIFY] [use-supabase-realtime.ts](file:///Users/likhith./Startup_Scope_AI/frontend/src/hooks/use-supabase-realtime.ts)

Extend to support:
- Message enrichment (join profile data for avatars/usernames)
- `validation_id` field on messages for inline LiveIdeaCard rendering

#### [NEW] [use-arena-feed.ts](file:///Users/likhith./Startup_Scope_AI/frontend/src/hooks/use-arena-feed.ts)

Hook for infinite-scroll feed loading with cursor-based pagination.

#### [NEW] [arena-store.ts](file:///Users/likhith./Startup_Scope_AI/frontend/src/stores/arena-store.ts)

Zustand store for Arena state:
- Active navigation item
- Active conversation
- Active group
- Composer state (idea text, poll, validation status)

---

### CSS Updates

#### [MODIFY] [globals.css](file:///Users/likhith./Startup_Scope_AI/frontend/src/app/globals.css)

Add new utility classes:
- `.glass-nav` — Left nav glassmorphism style
- `.streaming-pulse` — Pulsing animation for AI streaming state
- `.score-badge` variants (green/amber/red for feasibility scores)
- `.chat-bubble` — Message bubble styling
- `.action-menu` — Chat composer action menu popup

---

## User Review Required

> [!IMPORTANT]
> **Database Schema**: The current `messages` table has no `validation_id` column. For "Compute-as-a-Post" inside chat, we need to either:
> - **Option A**: Add a `validation_id UUID NULL` FK column to the `messages` table (recommended — clean, supports Supabase Realtime natively)
> - **Option B**: Encode the validation reference in the message `content` as a JSON string and parse client-side (hacky)
> 
> **Recommendation**: Option A. This requires a Supabase migration: `ALTER TABLE messages ADD COLUMN validation_id UUID REFERENCES validations(id);`

> [!WARNING]
> **Breaking Change**: The `(arena)/layout.tsx` will be completely rewritten. The old Discord-style Hub Rail + Channel Panel is being discarded entirely. Any existing pages under `(arena)/arena/hubs/` will need route changes.

> [!IMPORTANT]
> **Follows table**: The `follows` table already exists in the database with `follower_id` and `following_id`. We'll use it directly — no schema changes needed.

## Open Questions

> [!IMPORTANT]
> 1. **Should we add a `validation_id` column to the `messages` table?** This is required for rendering `LiveIdeaCard` inline in chat. Without it, we can't link a chat message to an AI validation result.

> [!NOTE]
> 2. **Should the old `/arena/hubs/[hubId]` route be preserved as a redirect to `/arena/groups/[hubId]`?** Or can we delete it cleanly?

> [!NOTE]
> 3. **Poll creation flow**: Should polls be creatable standalone in the feed composer, or only attached to AI validation posts? The `polls` table requires a `post_id` FK — polls can only exist on Arena posts.

---

## Verification Plan

### Automated Tests
- `npm run build` — Ensure no TypeScript compilation errors
- Run the dev server `npm run dev` and verify all routes render
- Browser verification: navigate each route (`/arena`, `/arena/messages`, `/arena/groups`, `/arena/explore`, `/arena/profile`)
- Verify the backend endpoints with `pytest` after adding new routers

### Manual Verification
- Screenshot each view at desktop (1440px) and mobile (390px) widths
- Test the LiveIdeaCard streaming lifecycle by submitting a real validation
- Test DM flow: init DM → send message → see realtime update
- Test Search: search by keyword, search by username
