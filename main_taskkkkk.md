# Arena Restructure — Task Tracker

## Phase 1: Backend — New Endpoints
- [ ] Add `validation_id` column reference in schemas (DB migration note)
- [ ] New schemas in `social.py` (search, DM, comments, group members, etc.)
- [ ] `search_router.py` — search + trending + suggested founders
- [ ] `dm_router.py` — conversations list, send message, message history
- [ ] `comments_router.py` — create + list comments
- [ ] Extend `community_router.py` — group members + leaderboard
- [ ] Register new routers in `social_app.py`

## Phase 2: Frontend — Layout & Design System
- [ ] Update `globals.css` with new utility classes
- [ ] Rewrite `(arena)/layout.tsx` — LinkedIn-style 3-column
- [ ] Create `arena-store.ts` — Zustand store for Arena state

## Phase 3: Frontend — Core Components
- [ ] `LiveIdeaCard.tsx` — Compute-as-a-Post with streaming state machine
- [ ] `StreamingProgress.tsx` — Animated AI pipeline progress
- [ ] `ChatTimeline.tsx` — Real-time chat with inline LiveIdeaCard
- [ ] `FounderCard.tsx` — Mini profile card
- [ ] `PollWidget.tsx` — Inline poll component
- [ ] `RightSidebar.tsx` — Context-aware sidebar

## Phase 4: Frontend — Pages
- [ ] Rewrite `arena/page.tsx` — Global Feed with composer
- [ ] `arena/messages/page.tsx` — DM interface
- [ ] `arena/groups/page.tsx` — Groups grid
- [ ] `arena/groups/[hubId]/page.tsx` — Group detail + chat
- [ ] `arena/explore/page.tsx` — Search & discover
- [ ] `arena/profile/page.tsx` — User profile

## Phase 5: Hooks & Integration
- [ ] `use-arena-feed.ts` — Infinite scroll hook
- [ ] Extend `use-supabase-realtime.ts` — validation_id support

## Phase 6: Verification
- [ ] `npm run build` passes
- [ ] All routes render
