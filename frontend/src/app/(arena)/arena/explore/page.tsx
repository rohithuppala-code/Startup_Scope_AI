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
        await api(`/api/v1/profiles/${targetUserId}/follow`, {
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
    <div className="max-w-2xl mx-auto px-5 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold gradient-text tracking-tight mb-2">Explore</h1>
        <p className="text-[15px] font-medium text-[var(--text-secondary)] leading-relaxed">
          Discover ideas by market gap and connect with top founders in the ecosystem.
        </p>
      </div>

      {/* Search Bar */}
      <div className="glass-card p-5 mb-5 shadow-lg bg-black/10">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-[var(--bg-glass)] flex items-center justify-center shrink-0 border border-[var(--border-subtle)]">
            <Search className="w-5 h-5 text-[var(--text-muted)]" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder={
              searchType === "posts"
                ? "Search ideas by keyword, market gap, or technology..."
                : "Search founders by username or display name..."
            }
            className="flex-1 bg-transparent text-base font-medium text-[var(--text-primary)] placeholder:text-[var(--text-muted)]/70 outline-none"
            autoFocus
          />
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleSearch}
            disabled={!query.trim() || loading}
            className="btn-primary text-sm py-2.5 px-6 font-semibold shadow-md disabled:opacity-50"
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
      <div className="tab-bar mb-8 w-fit p-1 bg-black/20">
        <button
          onClick={() => setSearchType("posts")}
          className={`tab-item py-2 px-5 font-semibold ${searchType === "posts" ? "tab-item-active shadow-md" : ""}`}
        >
          <Sparkles className="w-4 h-4 inline mr-2 text-[var(--accent-cyan)]" />
          Ideas
        </button>
        <button
          onClick={() => setSearchType("profiles")}
          className={`tab-item py-2 px-5 font-semibold ${searchType === "profiles" ? "tab-item-active shadow-md" : ""}`}
        >
          <Users2 className="w-4 h-4 inline mr-2 text-[var(--accent-violet)]" />
          Founders
        </button>
      </div>

      {/* Results */}
      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div
            key="loading"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="flex flex-col items-center justify-center py-20"
          >
            <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-violet)] mb-4" />
            <p className="text-sm font-medium text-[var(--text-muted)]">Searching the Arena...</p>
          </motion.div>
        ) : hasSearched ? (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            {/* Post Results */}
            {searchType === "posts" && (
              <div className="space-y-5">
                {postResults.length === 0 ? (
                  <div className="glass-card p-10 text-center border-dashed">
                    <Search className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3 opacity-50" />
                    <h3 className="text-base font-semibold text-[var(--text-primary)] tracking-tight mb-1">No ideas found</h3>
                    <p className="text-sm text-[var(--text-secondary)]">
                      No ideas matched your query &ldquo;<span className="text-[var(--text-primary)] font-medium">{query}</span>&rdquo;
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="text-sm font-semibold text-[var(--text-muted)] tracking-wider uppercase mb-2 ml-1">
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
              <div className="space-y-4">
                {profileResults.length === 0 ? (
                  <div className="glass-card p-10 text-center border-dashed">
                    <Users2 className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3 opacity-50" />
                    <h3 className="text-base font-semibold text-[var(--text-primary)] tracking-tight mb-1">No founders found</h3>
                    <p className="text-sm text-[var(--text-secondary)]">
                      No profiles matched your query &ldquo;<span className="text-[var(--text-primary)] font-medium">{query}</span>&rdquo;
                    </p>
                  </div>
                ) : (
                  <>
                    <p className="text-sm font-semibold text-[var(--text-muted)] tracking-wider uppercase mb-2 ml-1">
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
            className="text-center py-20"
          >
            <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mx-auto mb-6 border border-[var(--border-subtle)] shadow-xl shadow-violet-500/5">
              <TrendingUp className="w-10 h-10 text-[var(--text-muted)]" />
            </div>
            <h3 className="text-xl font-bold text-[var(--text-primary)] mb-2 tracking-tight">
              Discover the ecosystem
            </h3>
            <p className="text-base text-[var(--text-secondary)] max-w-md mx-auto leading-relaxed">
              Search for startup ideas by market gap, technology, or keyword. Find founders building in your space and expand your network.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
