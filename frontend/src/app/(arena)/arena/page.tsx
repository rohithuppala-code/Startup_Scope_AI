"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Zap,
  BarChart3,
  Loader2,
  Sparkles,
  TrendingUp,
  Filter,
} from "lucide-react";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";
import { useArenaFeed, type Post } from "@/hooks/use-arena-feed";
import LiveIdeaCard from "./components/LiveIdeaCard";

export default function ArenaFeedPage() {
  const userId = useUserStore((s) => s.userId);
  const { posts, loading, hasMore, loadMore, refreshFeed, prependPost } = useArenaFeed();
  const [composerText, setComposerText] = useState("");
  const [composerTags, setComposerTags] = useState("");
  const [composerTitle, setComposerTitle] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showComposer, setShowComposer] = useState(false);
  const [sortBy, setSortBy] = useState<"recent" | "top">("recent");
  const observerRef = useRef<HTMLDivElement>(null);

  // Initial load
  useEffect(() => {
    loadMore();
  }, [loadMore]);

  // Use refs to avoid recreating the observer
  const hasMoreRef = useRef(hasMore);
  const loadingRef = useRef(loading);
  useEffect(() => { hasMoreRef.current = hasMore; }, [hasMore]);
  useEffect(() => { loadingRef.current = loading; }, [loading]);

  // Infinite scroll observer
  useEffect(() => {
    if (!observerRef.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMoreRef.current && !loadingRef.current) {
          loadMore();
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(observerRef.current);
    return () => observer.disconnect();
  }, [loadMore]);

  const handleSubmitIdea = useCallback(async () => {
    if (!composerText.trim() || !userId || isSubmitting) return;
    setIsSubmitting(true);

    try {
      // Step 1: Submit to validation pipeline
      const valRes = await api<{ validation_id: string; status: string }>(
        "/api/v1/validate",
        {
          method: "POST",
          userId,
          body: {
            idea_description: composerText.trim(),
            target_market: null,
            budget_constraints: null,
          },
        }
      );

      // Step 2: Publish to Arena as a post immediately (it will be live-updated)
      const title = composerTitle.trim() || composerText.trim().slice(0, 80);
      const tags = composerTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);

      // Add a streaming card to the feed while validation runs
      prependPost({
        id: `temp-${valRes.validation_id}`,
        title: title,
        content: composerText.trim(),
        author_id: userId,
        author_username: "You",
        author_avatar: null,           // BUG FIX: field was missing; caused TS error
        karma_score: 0,
        upvote_count: 0,
        downvote_count: 0,
        comment_count: 0,
        tags: tags,
        created_at: new Date().toISOString(),
        validation_id: valRes.validation_id,
        report_json: null,
      } satisfies Post);

      // Reset composer
      setComposerText("");
      setComposerTitle("");
      setComposerTags("");
      setShowComposer(false);
    } catch (err) {
      console.error("[ArenaFeed] Submit error:", err);
    } finally {
      setIsSubmitting(false);
    }
  }, [composerText, composerTitle, composerTags, userId, isSubmitting, prependPost]);

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      {/* ─── Header ─── */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold gradient-text tracking-tight">Global Feed</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Battle-test ideas with the community
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="tab-bar">
            <button
              onClick={() => setSortBy("recent")}
              className={`tab-item ${sortBy === "recent" ? "tab-item-active" : ""}`}
            >
              <TrendingUp className="w-3 h-3 inline mr-1" />
              Recent
            </button>
            <button
              onClick={() => setSortBy("top")}
              className={`tab-item ${sortBy === "top" ? "tab-item-active" : ""}`}
            >
              <Filter className="w-3 h-3 inline mr-1" />
              Top
            </button>
          </div>
        </div>
      </div>

      {/* ─── Composer ─── */}
      <motion.div
        className="composer p-4 mb-8"
        layout
      >
        {!showComposer ? (
          <button
            onClick={() => setShowComposer(true)}
            className="w-full text-left text-[var(--text-muted)] text-sm hover:text-[var(--text-secondary)] transition-colors py-1.5"
          >
            💡 What are you building? Share an idea for AI validation...
          </button>
        ) : (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="space-y-4"
          >
            {/* Title */}
            <input
              type="text"
              value={composerTitle}
              onChange={(e) => setComposerTitle(e.target.value)}
              placeholder="Give your idea a title..."
              className="w-full bg-transparent text-lg font-semibold text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none tracking-tight"
            />

            {/* Description */}
            <textarea
              value={composerText}
              onChange={(e) => setComposerText(e.target.value)}
              placeholder="Describe your startup idea in detail. Our AI will analyze competitors, pricing, patents, and more..."
              rows={4}
              className="w-full bg-transparent text-sm text-[var(--text-secondary)] placeholder:text-[var(--text-muted)] outline-none resize-none leading-relaxed"
              autoFocus
            />

            {/* Tags */}
            <input
              type="text"
              value={composerTags}
              onChange={(e) => setComposerTags(e.target.value)}
              placeholder="Tags (comma separated): SaaS, B2B, AI..."
              className="w-full bg-transparent text-xs text-[var(--text-muted)] placeholder:text-[var(--text-muted)]/50 outline-none"
            />

            {/* Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-[var(--border-subtle)]">
              <div className="flex items-center gap-2">
                <button className="btn-ghost text-xs py-1.5 px-3 flex items-center gap-1.5">
                  <BarChart3 className="w-3.5 h-3.5" />
                  Attach Poll
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowComposer(false)}
                  className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors px-3 py-1.5"
                >
                  Cancel
                </button>
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleSubmitIdea}
                  disabled={!composerText.trim() || isSubmitting}
                  className="btn-primary text-xs py-2 px-4 flex items-center gap-1.5 disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Submitting...
                    </>
                  ) : (
                    <>
                      <Zap className="w-3.5 h-3.5" />
                      Run AI Validation
                    </>
                  )}
                </motion.button>
              </div>
            </div>
          </motion.div>
        )}
      </motion.div>

      {/* ─── Feed ─── */}
      <div className="space-y-5">
        <AnimatePresence mode="popLayout">
          {posts.map((post, i) => {
            // Detect if this is a live streaming card
            const isStreaming = post.id.startsWith("temp-");

            return (
              <motion.div
                key={post.id}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i < 5 ? i * 0.04 : 0 }}
              >
                <LiveIdeaCard
                  postId={isStreaming ? undefined : post.id}
                  title={post.title}
                  content={post.content}
                  authorId={post.author_id}
                  authorUsername={post.author_username}
                  upvoteCount={post.upvote_count}
                  downvoteCount={post.downvote_count}
                  commentCount={post.comment_count}
                  tags={post.tags}
                  createdAt={post.created_at}
                  reportJson={post.report_json}
                  validationId={post.validation_id}
                  karmaScore={post.karma_score}
                  initialPhase={isStreaming ? "streaming" : "interactive"}
                  ideaDescription={post.content}
                  onPhaseChange={(phase) => {
                    if (phase === "completed" && isStreaming && userId && post.validation_id) {
                      // BUG FIX: auto-publish races with the Celery worker updating
                      // the DB status to "completed". The publish endpoint rejects
                      // with 422 if status !== "completed". Retry with backoff.
                      const publish = async (attempt = 1) => {
                        try {
                          await api("/api/v1/arena/publish", {
                            method: "POST",
                            userId,
                            body: {
                              validation_id: post.validation_id,
                              title: post.title || "Startup Idea",
                              tags: post.tags,
                            },
                          });
                        } catch (err: unknown) {
                          const msg = err instanceof Error ? err.message : String(err);
                          if (msg.includes("409")) return; // Already published — ok
                          if (msg.includes("422") && attempt < 5) {
                            // Worker hasn't committed completed status yet — retry
                            setTimeout(() => publish(attempt + 1), attempt * 3000);
                          } else {
                            console.warn("[ArenaFeed] Auto-publish failed:", msg);
                          }
                        }
                      };
                      publish();
                    }
                  }}
                />
              </motion.div>
            );
          })}
        </AnimatePresence>

        {/* Loading more */}
        {loading && (
          <div className="flex justify-center py-10">
            <Loader2 className="w-6 h-6 text-[var(--accent-violet)] animate-spin" />
          </div>
        )}

        {/* Infinite scroll trigger */}
        <div ref={observerRef} className="h-px" />

        {/* Empty state */}
        {!loading && posts.length === 0 && (
          <div className="text-center py-20">
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mx-auto mb-5 border border-[var(--border-subtle)]">
              <Sparkles className="w-8 h-8 text-[var(--text-muted)]" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-1.5 tracking-tight">
              The Arena awaits
            </h3>
            <p className="text-sm text-[var(--text-secondary)] max-w-xs mx-auto leading-relaxed">
              Be the first to share an idea and get it validated by our AI pipeline.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
