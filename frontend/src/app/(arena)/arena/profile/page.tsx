"use client";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  User,
  Star,
  TrendingUp,
  Edit3,
  Loader2,
  ExternalLink,
  Globe,
  Link2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";
import LiveIdeaCard from "../components/LiveIdeaCard";

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
  content: string;
  author_id: string;
  author_username: string;
  karma_score: number;
  upvote_count: number;
  downvote_count: number;
  comment_count: number;
  tags: string[];
  created_at: string;
  validation_id?: string | null;
  report_json?: Record<string, unknown> | null;
}

export default function ProfilePage() {
  const userId = useUserStore((s) => s.userId);
  const karma = useUserStore((s) => s.karma);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    display_name: "",
    bio: "",
    twitter_url: "",
    linkedin_url: "",
    github_url: "",
    website_url: "",
  });

  useEffect(() => {
    if (!userId) return;
    const loadProfile = async () => {
      try {
        const myProfile = await api<Profile>("/api/v1/profiles/me", { userId });
        setProfile(myProfile);
        setEditForm({
          display_name: myProfile.display_name || "",
          bio: myProfile.bio || "",
          twitter_url: myProfile.twitter_url || "",
          linkedin_url: myProfile.linkedin_url || "",
          github_url: myProfile.github_url || "",
          website_url: myProfile.website_url || "",
        });

        // Try fetching by user_id's published posts
        const postsData = await api<Post[]>(`/api/v1/profiles/${userId}/validations`);
        setPosts(postsData);
      } catch (e) {
        console.error("Failed to load profile", e);
      }
      setLoading(false);
    };
    loadProfile();
  }, [userId]);

  const handleSave = async () => {
    if (!userId) return;
    try {
      const payload: Record<string, string> = {};
      if (editForm.display_name) payload.display_name = editForm.display_name;
      if (editForm.bio) payload.bio = editForm.bio;
      if (editForm.twitter_url) payload.twitter_url = editForm.twitter_url;
      if (editForm.linkedin_url) payload.linkedin_url = editForm.linkedin_url;
      if (editForm.github_url) payload.github_url = editForm.github_url;
      if (editForm.website_url) payload.website_url = editForm.website_url;

      if (Object.keys(payload).length === 0) return;

      const updated = await api<Profile>("/api/v1/profiles/me", {
        method: "PUT",
        userId,
        body: payload,
      });
      setProfile(updated);
      useUserStore.getState().setProfileInfo(updated.display_name || null, updated.username, updated.avatar_url || null);
      setEditing(false);
    } catch (err) {
      console.error("[Profile] Save error:", err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--accent-violet)]" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      {/* Profile Header */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-6 mb-6"
      >
        <div className="flex items-start gap-4">
          <div className="avatar avatar-lg">
            {profile?.avatar_url ? (
              <img src={profile.avatar_url} alt="" />
            ) : (
              <User className="w-6 h-6" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h1 className="text-xl font-bold text-[var(--text-primary)]">
                  {profile?.display_name || "Founder"}
                </h1>
                <p className="text-sm text-[var(--accent-violet)]">
                  @{profile?.username || userId?.slice(0, 8)}
                </p>
              </div>
              <button
                onClick={() => setEditing(!editing)}
                className="btn-ghost text-xs flex items-center gap-1.5"
              >
                <Edit3 className="w-3.5 h-3.5" />
                Edit
              </button>
            </div>

            {profile?.bio && (
              <p className="text-sm text-[var(--text-secondary)] mt-2">{profile.bio}</p>
            )}

            {/* Stats */}
            <div className="flex items-center gap-6 mt-4">
              <div className="flex items-center gap-1.5">
                <Star className="w-4 h-4 text-amber-400" />
                <span className="text-lg font-bold text-amber-400">{karma}</span>
                <span className="text-xs text-[var(--text-muted)]">karma</span>
              </div>
              <div className="flex items-center gap-1.5">
                <TrendingUp className="w-4 h-4 text-[var(--accent-emerald)]" />
                <span className="text-lg font-bold text-[var(--accent-emerald)]">{posts.length}</span>
                <span className="text-xs text-[var(--text-muted)]">ideas shared</span>
              </div>
            </div>

            {/* Social Links */}
            {profile && (
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
            )}

            {/* Badges */}
            {profile?.badges && profile.badges.length > 0 && (
              <div className="flex items-center gap-2 mt-3">
                {profile.badges.map((badge) => (
                  <span
                    key={badge}
                    className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/10"
                  >
                    {badge === "first_post" ? "🌱" : badge === "serial_builder" ? "🏗️" : badge === "karma_100" ? "⚡" : badge === "karma_500" ? "🚀" : "👍"}
                    {badge.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Edit Form */}
        {editing && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            className="mt-4 pt-4 border-t border-[var(--border-subtle)] space-y-3"
          >
            <input
              type="text"
              value={editForm.display_name}
              onChange={(e) => setEditForm((f) => ({ ...f, display_name: e.target.value }))}
              placeholder="Display name"
              className="input-dark text-sm"
            />
            <textarea
              value={editForm.bio}
              onChange={(e) => setEditForm((f) => ({ ...f, bio: e.target.value }))}
              placeholder="Bio (max 500 characters)"
              className="input-dark text-sm"
              rows={3}
            />
            <div className="grid grid-cols-2 gap-2">
              <input
                type="url"
                value={editForm.twitter_url}
                onChange={(e) => setEditForm((f) => ({ ...f, twitter_url: e.target.value }))}
                placeholder="Twitter URL"
                className="input-dark text-xs"
              />
              <input
                type="url"
                value={editForm.linkedin_url}
                onChange={(e) => setEditForm((f) => ({ ...f, linkedin_url: e.target.value }))}
                placeholder="LinkedIn URL"
                className="input-dark text-xs"
              />
              <input
                type="url"
                value={editForm.github_url}
                onChange={(e) => setEditForm((f) => ({ ...f, github_url: e.target.value }))}
                placeholder="GitHub URL"
                className="input-dark text-xs"
              />
              <input
                type="url"
                value={editForm.website_url}
                onChange={(e) => setEditForm((f) => ({ ...f, website_url: e.target.value }))}
                placeholder="Website URL"
                className="input-dark text-xs"
              />
            </div>
            <div className="flex gap-2">
              <button onClick={handleSave} className="btn-primary text-xs py-2 px-4">
                Save Changes
              </button>
              <button
                onClick={() => setEditing(false)}
                className="btn-ghost text-xs py-2 px-4"
              >
                Cancel
              </button>
            </div>
          </motion.div>
        )}
      </motion.div>

      {/* Published Ideas */}
      <div>
        <h2 className="text-lg font-bold text-[var(--text-primary)] mb-4">
          Published Ideas
        </h2>
        {posts.length === 0 ? (
          <div className="text-center py-12 glass-card">
            <TrendingUp className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-2" />
            <p className="text-sm text-[var(--text-secondary)]">
              No ideas published yet
            </p>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Share your first idea from the Global Feed!
            </p>
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
                content={post.content}
                validationId={post.validation_id}
                reportJson={post.report_json}
                initialPhase="interactive"
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
