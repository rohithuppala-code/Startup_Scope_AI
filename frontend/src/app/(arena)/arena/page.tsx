"use client";
import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";
import {
  ArrowBigUp,
  ArrowBigDown,
  MessageSquare,
  Tag,
  Sparkles,
  BarChart3,
} from "lucide-react";

interface Post {
  id: string;
  title: string;
  author_username: string;
  karma_score: number;
  upvote_count: number;
  downvote_count: number;
  comment_count: number;
  tags: string[];
  created_at: string;
}

export default function ArenaFeedPage() {
  const userId = useUserStore((s) => s.userId);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Post[]>("/api/v1/arena/posts?page=1&page_size=30")
      .then(setPosts)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const vote = async (postId: string, direction: 1 | -1) => {
    if (!userId) return;
    try {
      const res = await api<{ new_score: number }>(
        `/api/v1/arena/posts/${postId}/vote`,
        { method: "POST", userId, body: { direction } }
      );
      setPosts((prev) =>
        prev.map((p) =>
          p.id === postId
            ? {
                ...p,
                karma_score: res.new_score,
                upvote_count:
                  direction === 1 ? p.upvote_count + 1 : p.upvote_count,
                downvote_count:
                  direction === -1 ? p.downvote_count + 1 : p.downvote_count,
              }
            : p
        )
      );
    } catch (err) {
      console.error("Vote error:", err);
    }
  };

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="glass-card p-6 animate-pulse">
            <div className="h-5 w-64 bg-white/5 rounded mb-3" />
            <div className="h-3 w-40 bg-white/5 rounded mb-2" />
            <div className="h-3 w-full bg-white/5 rounded" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold gradient-text">Validation Arena</h1>
          <p className="text-sm text-[var(--text-secondary)]">
            Battle-test ideas with the community
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <BarChart3 className="w-4 h-4" />
          {posts.length} posts
        </div>
      </div>

      <AnimatePresence mode="popLayout">
        {posts.map((post, i) => (
          <motion.div
            key={post.id}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
            className="glass-card glass-card-hover p-5 mb-4"
          >
            <div className="flex gap-4">
              {/* Vote Column */}
              <div className="flex flex-col items-center gap-0.5 shrink-0">
                <button
                  onClick={() => vote(post.id, 1)}
                  className="p-1.5 rounded-lg hover:bg-emerald-500/10 transition-colors group"
                >
                  <ArrowBigUp className="w-5 h-5 text-[var(--text-muted)] group-hover:text-emerald-400 transition-colors" />
                </button>
                <span
                  className={`text-sm font-bold tabular-nums ${
                    post.karma_score > 0
                      ? "text-emerald-400"
                      : post.karma_score < 0
                      ? "text-rose-400"
                      : "text-[var(--text-muted)]"
                  }`}
                >
                  {post.karma_score}
                </span>
                <button
                  onClick={() => vote(post.id, -1)}
                  className="p-1.5 rounded-lg hover:bg-rose-500/10 transition-colors group"
                >
                  <ArrowBigDown className="w-5 h-5 text-[var(--text-muted)] group-hover:text-rose-400 transition-colors" />
                </button>
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold text-base mb-1 text-[var(--text-primary)]">
                  {post.title}
                </h3>
                <p className="text-xs text-[var(--text-muted)] mb-3">
                  by{" "}
                  <span className="text-[var(--accent-violet)] font-medium">
                    @{post.author_username}
                  </span>{" "}
                  · {new Date(post.created_at).toLocaleDateString()}
                </p>

                {/* Tags */}
                {(post.tags || []).length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    {post.tags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1 text-xs px-2.5 py-0.5 rounded-full bg-violet-500/10 text-violet-300 border border-violet-500/10"
                      >
                        <Tag className="w-3 h-3" />
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {/* Footer */}
                <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
                  <span className="flex items-center gap-1">
                    <MessageSquare className="w-3.5 h-3.5" />
                    {post.comment_count} comments
                  </span>
                  <span className="flex items-center gap-1">
                    <Sparkles className="w-3.5 h-3.5" />
                    AI Synthesis
                  </span>
                </div>
              </div>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>

      {posts.length === 0 && (
        <div className="text-center py-20">
          <Sparkles className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3" />
          <p className="text-[var(--text-secondary)]">
            No ideas in the Arena yet. Be the first to publish!
          </p>
        </div>
      )}
    </div>
  );
}
