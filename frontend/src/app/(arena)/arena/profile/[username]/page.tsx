"use client";
import { useState, useEffect, use } from "react";
import { motion } from "framer-motion";
import { User, Star, TrendingUp, Loader2, ExternalLink, Globe, Link2 } from "lucide-react";
import { api } from "@/lib/api";
import LiveIdeaCard from "../../components/LiveIdeaCard";
import { useUserStore } from "@/stores/user-store";

interface Profile {
  id: string;
  username: string;
  display_name: string | null;
  bio: string | null;
  avatar_url: string | null;
  karma_score: number;
  badges: string[];
  twitter_url: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  website_url: string | null;
  created_at: string;
}

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

export default function OtherProfilePage({ params }: { params: Promise<{ username: string }> }) {
  const { username } = use(params);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [isFollowing, setIsFollowing] = useState(false);
  const [followerCount, setFollowerCount] = useState(0);
  const [isFollowingLoading, setIsFollowingLoading] = useState(false);
  const currentUserId = useUserStore((s) => s.userId);

  useEffect(() => {
    const loadProfile = async () => {
      try {
        const p = await api<Profile>(`/api/v1/profiles/${username}`);
        setProfile(p);
        const postsData = await api<Post[]>(`/api/v1/profiles/${p.id}/validations`);
        setPosts(postsData);

        if (currentUserId && currentUserId !== p.id) {
          const followData = await api<{ is_following: boolean }>(`/api/v1/profiles/${p.id}/is_following`, { userId: currentUserId });
          setIsFollowing(followData.is_following);
        }

        const countData = await api<{ follower_count: number }>(`/api/v1/profiles/${p.id}/followers/count`);
        setFollowerCount(countData.follower_count);
      } catch (err) {
        console.error("Profile not found", err);
      } finally {
        setLoading(false);
      }
    };
    loadProfile();
  }, [username, currentUserId]);

  const handleFollow = async () => {
    if (!profile || !currentUserId) return;
    setIsFollowingLoading(true);
    try {
      const res = await api<{ status: string }>(`/api/v1/profiles/${profile.id}/follow`, {
        method: "POST",
        userId: currentUserId,
      });
      const followingNow = res.status === "followed";
      setIsFollowing(followingNow);
      setFollowerCount((prev) => followingNow ? prev + 1 : prev - 1);
    } catch (err) {
      console.error("Failed to toggle follow", err);
    } finally {
      setIsFollowingLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-violet)]" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center">
        <div className="w-20 h-20 rounded-3xl bg-red-500/10 flex items-center justify-center mb-4 border border-red-500/20">
          <User className="w-10 h-10 text-red-400" />
        </div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight">Profile Not Found</h1>
        <p className="text-sm font-medium text-[var(--text-secondary)] mt-2">The user @{username} does not exist.</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-5 py-8">
      {/* Profile Header */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 mb-8 shadow-xl border-[var(--border-subtle)] relative overflow-hidden">
        {/* Decorative Background Blob */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-violet-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3 pointer-events-none" />
        
        <div className="flex items-start gap-6 relative z-10">
          <div className="avatar avatar-xl shadow-lg shadow-violet-500/20 ring-4 ring-black/20">
            {profile.avatar_url ? <img src={profile.avatar_url} alt="" /> : <User className="w-8 h-8 text-[var(--text-muted)]" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-4 mb-1">
              <div>
                <h1 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight">{profile.display_name || "Founder"}</h1>
                <p className="text-[15px] font-semibold text-[var(--accent-violet)]">@{profile.username}</p>
              </div>
              {currentUserId !== profile.id && (
                <button
                  onClick={handleFollow}
                  disabled={isFollowingLoading}
                  className={`btn-primary text-sm py-2 px-6 font-semibold shadow-md transition-all ${isFollowing ? "bg-white/10 text-[var(--text-primary)] border border-[var(--border-subtle)] hover:bg-white/20" : "shadow-violet-500/30"}`}
                >
                  {isFollowingLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : isFollowing ? "Following" : "Follow"}
                </button>
              )}
            </div>

            {profile.bio && <p className="text-[15px] text-[var(--text-secondary)] mt-3 leading-relaxed">{profile.bio}</p>}

            {/* Stats */}
            <div className="flex items-center gap-6 mt-6 p-4 rounded-2xl bg-black/20 border border-[var(--border-subtle)]">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-400/10 flex items-center justify-center border border-amber-400/20">
                  <Star className="w-5 h-5 text-amber-400" />
                </div>
                <div>
                  <div className="text-xl font-extrabold text-amber-400 leading-none mb-1">{profile.karma_score || 0}</div>
                  <div className="text-[11px] font-semibold tracking-widest uppercase text-[var(--text-muted)]">Karma</div>
                </div>
              </div>
              <div className="w-px h-10 bg-[var(--border-subtle)]" />
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-cyan-400/10 flex items-center justify-center border border-cyan-400/20">
                  <User className="w-5 h-5 text-cyan-400" />
                </div>
                <div>
                  <div className="text-xl font-extrabold text-cyan-400 leading-none mb-1">{followerCount}</div>
                  <div className="text-[11px] font-semibold tracking-widest uppercase text-[var(--text-muted)]">Followers</div>
                </div>
              </div>
              <div className="w-px h-10 bg-[var(--border-subtle)]" />
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-400/10 flex items-center justify-center border border-emerald-400/20">
                  <TrendingUp className="w-5 h-5 text-emerald-400" />
                </div>
                <div>
                  <div className="text-xl font-extrabold text-emerald-400 leading-none mb-1">{posts.length}</div>
                  <div className="text-[11px] font-semibold tracking-widest uppercase text-[var(--text-muted)]">Ideas</div>
                </div>
              </div>
            </div>

            {/* Badges & Links Row */}
            <div className="flex items-center justify-between mt-6">
              {/* Badges */}
              <div className="flex items-center gap-2">
                {profile.badges && profile.badges.length > 0 && profile.badges.map((badge) => (
                  <span key={badge} className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 shadow-sm capitalize tracking-tight">
                    {badge === "first_post" ? "🌱" : badge === "serial_builder" ? "🏗️" : badge === "karma_100" ? "⚡" : badge === "karma_500" ? "🚀" : "👍"}
                    {badge.replace(/_/g, " ")}
                  </span>
                ))}
              </div>

              {/* Social Links */}
              <div className="flex items-center gap-2">
                {profile.twitter_url && (
                  <a href={profile.twitter_url} target="_blank" rel="noopener" className="w-9 h-9 rounded-xl flex items-center justify-center bg-white/5 border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-cyan-400 hover:border-cyan-400/30 hover:bg-cyan-400/10 transition-all shadow-sm" title="Twitter / X">
                    <Link2 className="w-4 h-4" />
                  </a>
                )}
                {profile.linkedin_url && (
                  <a href={profile.linkedin_url} target="_blank" rel="noopener" className="w-9 h-9 rounded-xl flex items-center justify-center bg-white/5 border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-blue-400 hover:border-blue-400/30 hover:bg-blue-400/10 transition-all shadow-sm" title="LinkedIn">
                    <Link2 className="w-4 h-4" />
                  </a>
                )}
                {profile.github_url && (
                  <a href={profile.github_url} target="_blank" rel="noopener" className="w-9 h-9 rounded-xl flex items-center justify-center bg-white/5 border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-white hover:border-white/30 hover:bg-white/10 transition-all shadow-sm" title="GitHub">
                    <ExternalLink className="w-4 h-4" />
                  </a>
                )}
                {profile.website_url && (
                  <a href={profile.website_url} target="_blank" rel="noopener" className="w-9 h-9 rounded-xl flex items-center justify-center bg-white/5 border border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-emerald-400 hover:border-emerald-400/30 hover:bg-emerald-400/10 transition-all shadow-sm" title="Website">
                    <Globe className="w-4 h-4" />
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Published Ideas */}
      <div>
        <div className="flex items-center gap-3 mb-6">
          <h2 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">Published Ideas</h2>
          <div className="h-px flex-1 bg-[var(--border-subtle)]" />
        </div>
        
        {posts.length === 0 ? (
          <div className="text-center py-16 glass-card border-dashed">
            <TrendingUp className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3 opacity-50" />
            <h3 className="text-base font-semibold text-[var(--text-primary)] tracking-tight mb-1">No ideas published yet</h3>
            <p className="text-sm font-medium text-[var(--text-secondary)]">This founder hasn't shared any validated ideas.</p>
          </div>
        ) : (
          <div className="space-y-5">
            {posts.map((post) => (
              <LiveIdeaCard
                key={post.id}
                postId={post.id}
                title={post.title}
                authorUsername={post.author_username}
                upvoteCount={post.upvote_count}
                downvoteCount={post.downvote_count}
                commentCount={post.comment_count}
                tags={post.tags}
                createdAt={post.created_at}
                karmaScore={post.karma_score}
                initialPhase="interactive"
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
