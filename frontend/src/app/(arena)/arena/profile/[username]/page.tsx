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
        <Loader2 className="w-6 h-6 animate-spin text-[var(--accent-violet)]" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">Profile Not Found</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-2">The user @{username} does not exist.</p>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      {/* Profile Header */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-6 mb-6">
        <div className="flex items-start gap-4">
          <div className="avatar avatar-lg">
            {profile.avatar_url ? <img src={profile.avatar_url} alt="" /> : <User className="w-6 h-6" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h1 className="text-xl font-bold text-[var(--text-primary)]">{profile.display_name || "Founder"}</h1>
                <p className="text-sm text-[var(--accent-violet)]">@{profile.username}</p>
              </div>
              {currentUserId !== profile.id && (
                <button
                  onClick={handleFollow}
                  disabled={isFollowingLoading}
                  className={`btn-primary text-xs flex items-center gap-1.5 ${isFollowing ? "opacity-75" : ""}`}
                >
                  {isFollowing ? "Following" : "Follow"}
                </button>
              )}
            </div>

            {profile.bio && <p className="text-sm text-[var(--text-secondary)] mt-2">{profile.bio}</p>}

            {/* Stats */}
            <div className="flex items-center gap-6 mt-4">
              <div className="flex items-center gap-1.5">
                <Star className="w-4 h-4 text-amber-400" />
                <span className="text-lg font-bold text-amber-400">{profile.karma_score || 0}</span>
                <span className="text-xs text-[var(--text-muted)]">karma</span>
              </div>
              <div className="flex items-center gap-1.5">
                <User className="w-4 h-4 text-cyan-400" />
                <span className="text-lg font-bold text-cyan-400">{followerCount}</span>
                <span className="text-xs text-[var(--text-muted)]">followers</span>
              </div>
              <div className="flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-[var(--accent-emerald)]" />
                <span className="text-lg font-bold text-[var(--accent-emerald)]">{posts.length}</span>
                <span className="text-xs text-[var(--text-muted)]">ideas shared</span>
              </div>
            </div>

            {/* Social Links */}
            <div className="flex items-center gap-3 mt-3">
              {profile.twitter_url && (
                <a href={profile.twitter_url} target="_blank" rel="noopener" className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--accent-cyan)] transition-colors" title="Twitter / X">
                  <Link2 className="w-3.5 h-3.5" />
                  <span>Twitter</span>
                </a>
              )}
              {profile.linkedin_url && (
                <a href={profile.linkedin_url} target="_blank" rel="noopener" className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--accent-cyan)] transition-colors" title="LinkedIn">
                  <Link2 className="w-3.5 h-3.5" />
                  <span>LinkedIn</span>
                </a>
              )}
              {profile.github_url && (
                <a href={profile.github_url} target="_blank" rel="noopener" className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--accent-cyan)] transition-colors" title="GitHub">
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>GitHub</span>
                </a>
              )}
              {profile.website_url && (
                <a href={profile.website_url} target="_blank" rel="noopener" className="text-[var(--text-muted)] hover:text-[var(--accent-cyan)] transition-colors">
                  <Globe className="w-4 h-4" />
                </a>
              )}
            </div>

            {/* Badges */}
            {profile.badges && profile.badges.length > 0 && (
              <div className="flex items-center gap-2 mt-3">
                {profile.badges.map((badge) => (
                  <span key={badge} className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/10">
                    {badge === "first_post" ? "🌱" : badge === "serial_builder" ? "🏗️" : badge === "karma_100" ? "⚡" : badge === "karma_500" ? "🚀" : "👍"}
                    {badge.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* Published Ideas */}
      <div>
        <h2 className="text-lg font-bold text-[var(--text-primary)] mb-4">Published Ideas</h2>
        {posts.length === 0 ? (
          <div className="text-center py-12 glass-card">
            <TrendingUp className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-2" />
            <p className="text-sm text-[var(--text-secondary)]">No ideas published yet</p>
          </div>
        ) : (
          <div className="space-y-4">
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
