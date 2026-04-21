"use client";
import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Sparkles,
  Users2,
  TrendingUp,
  Loader2,
  Tag,
} from "lucide-react";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";
import LiveIdeaCard from "../components/LiveIdeaCard";
import FounderCard from "../components/FounderCard";

interface SearchPost {
  id: string;
  title: string | null;
  content: string;
  author_username: string;
  upvote_count: number;
  downvote_count: number;
  comment_count: number;
  tags: string[];
  created_at: string;
}

interface SearchProfile {
  id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  bio: string | null;
  karma_score: number;
  badges: string[];
}

export default function ExplorePage() {
  const userId = useUserStore((s) => s.userId);
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState<"posts" | "profiles">("posts");
  const [postResults, setPostResults] = useState<SearchPost[]>([]);
  const [profileResults, setProfileResults] = useState<SearchProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setHasSearched(true);
    try {
      if (searchType === "posts") {
        const data = await api<SearchPost[]>(
          `/api/v1/arena/search?q=${encodeURIComponent(query.trim())}&type=posts`
        );
        setPostResults(data);
        setProfileResults([]);
      } else {
        const data = await api<SearchProfile[]>(
          `/api/v1/arena/search?q=${encodeURIComponent(query.trim())}&type=profiles`
        );
        setProfileResults(data);
        setPostResults([]);
      }
    } catch (err) {
      console.error("[Explore] Search error:", err);
    } finally {
      setLoading(false);
    }
  }, [query, searchType]);

  const handleFollow = useCallback(
    async (targetUserId: string) => {
      if (!userId) return;
      try {
        await api(`/api/v1/follows/${targetUserId}`, {
          method: "POST",
          userId,
        });
      } catch (err) {
        console.error("[Explore] Follow error:", err);
      }
    },
    [userId]
  );

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold gradient-text mb-1">Explore</h1>
        <p className="text-sm text-[var(--text-secondary)]">
          Discover ideas by market gap and connect with founders
        </p>
      </div>

      {/* Search Bar */}
      <div className="composer p-4 mb-4">
        <div className="flex items-center gap-3">
          <Search className="w-5 h-5 text-[var(--text-muted)] shrink-0" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder={
              searchType === "posts"
                ? "Search ideas by keyword, market gap..."
                : "Search founders by username..."
            }
            className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none"
            autoFocus
          />
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleSearch}
            disabled={!query.trim() || loading}
            className="btn-primary text-xs py-2 px-4"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              "Search"
            )}
          </motion.button>
        </div>
      </div>

      {/* Type Toggle */}
      <div className="tab-bar mb-6 w-fit">
        <button
          onClick={() => setSearchType("posts")}
          className={`tab-item ${searchType === "posts" ? "tab-item-active" : ""}`}
        >
          <Sparkles className="w-3 h-3 inline mr-1" />
          Ideas
        </button>
        <button
          onClick={() => setSearchType("profiles")}
          className={`tab-item ${searchType === "profiles" ? "tab-item-active" : ""}`}
        >
          <Users2 className="w-3 h-3 inline mr-1" />
          Founders
        </button>
      </div>

      {/* Results */}
      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex justify-center py-12"
          >
            <Loader2 className="w-6 h-6 animate-spin text-[var(--accent-violet)]" />
          </motion.div>
        ) : hasSearched ? (
          <motion.div
            key="results"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >
            {/* Post Results */}
            {searchType === "posts" && (
              <div className="space-y-4">
                {postResults.length === 0 ? (
                  <div className="text-center py-12">
                    <Search className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-2" />
                    <p className="text-sm text-[var(--text-secondary)]">
                      No ideas found for &ldquo;{query}&rdquo;
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="text-xs text-[var(--text-muted)] mb-2">
                      {postResults.length} result{postResults.length !== 1 ? "s" : ""}
                    </p>
                    {postResults.map((post) => (
                      <LiveIdeaCard
                        key={post.id}
                        postId={post.id}
                        title={post.title || undefined}
                        content={post.content}
                        authorUsername={post.author_username}
                        upvoteCount={post.upvote_count}
                        downvoteCount={post.downvote_count}
                        commentCount={post.comment_count}
                        tags={post.tags}
                        createdAt={post.created_at}
                        initialPhase="interactive"
                      />
                    ))}
                  </>
                )}
              </div>
            )}

            {/* Profile Results */}
            {searchType === "profiles" && (
              <div className="space-y-3">
                {profileResults.length === 0 ? (
                  <div className="text-center py-12">
                    <Users2 className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-2" />
                    <p className="text-sm text-[var(--text-secondary)]">
                      No founders found for &ldquo;{query}&rdquo;
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="text-xs text-[var(--text-muted)] mb-2">
                      {profileResults.length} founder{profileResults.length !== 1 ? "s" : ""}
                    </p>
                    {profileResults.map((profile) => (
                      <FounderCard
                        key={profile.id}
                        id={profile.id}
                        username={profile.username}
                        displayName={profile.display_name}
                        avatarUrl={profile.avatar_url}
                        bio={profile.bio}
                        karmaScore={profile.karma_score}
                        badges={profile.badges}
                        onFollow={handleFollow}
                      />
                    ))}
                  </>
                )}
              </div>
            )}
          </motion.div>
        ) : (
          /* Discovery / Pre-Search State */
          <motion.div
            key="discovery"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-16"
          >
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mx-auto mb-4 border border-[var(--border-subtle)]">
              <TrendingUp className="w-8 h-8 text-[var(--text-muted)]" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-1">
              Discover the ecosystem
            </h3>
            <p className="text-sm text-[var(--text-secondary)] max-w-sm mx-auto">
              Search for startup ideas by market gap, technology, or keyword. Find founders building in your space.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
