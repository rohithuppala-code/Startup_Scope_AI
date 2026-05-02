"use client";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { User, Star, ExternalLink, Users2 } from "lucide-react";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";

interface FounderCardProps {
  id: string;
  username: string;
  displayName?: string | null;
  avatarUrl?: string | null;
  bio?: string | null;
  karmaScore: number;
  badges?: string[];
  compact?: boolean;
  onFollow?: (userId: string) => void;
  onMessage?: (userId: string) => void;
  followerCount?: number;
}

export default function FounderCard({
  id,
  username,
  displayName,
  avatarUrl,
  bio,
  karmaScore,
  badges = [],
  compact = false,
  onFollow,
  onMessage,
  followerCount = 0,
}: FounderCardProps) {
  const [isFollowing, setIsFollowing] = useState(false);
  const [localFollowerCount, setLocalFollowerCount] = useState(followerCount);
  const [loading, setLoading] = useState(false);
  const currentUserId = useUserStore((s) => s.userId);

  useEffect(() => {
    // Fetch follower count
    api<{ follower_count: number }>(`/api/v1/profiles/${id}/followers/count`)
      .then((res) => setLocalFollowerCount(res.follower_count))
      .catch(console.error);

    // Fetch follow status
    if (currentUserId && currentUserId !== id) {
      api<{ is_following: boolean }>(`/api/v1/profiles/${id}/is_following`, { userId: currentUserId })
        .then((res) => setIsFollowing(res.is_following))
        .catch(console.error);
    }
  }, [id, currentUserId]);

  const handleFollowClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!currentUserId || loading) return;
    setLoading(true);
    try {
      const res = await api<{ status: string }>(`/api/v1/profiles/${id}/follow`, {
        method: "POST",
        userId: currentUserId,
      });
      const followingNow = res.status === "followed";
      setIsFollowing(followingNow);
      setLocalFollowerCount((prev) => followingNow ? prev + 1 : prev - 1);
      if (onFollow) onFollow(id);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (compact) {
    return (
      <motion.div
        whileHover={{ x: 2, backgroundColor: "rgba(255, 255, 255, 0.03)" }}
        className="flex items-center gap-3 p-2.5 rounded-xl transition-all cursor-pointer border border-transparent hover:border-[var(--border-subtle)]"
      >
        <div className="avatar avatar-sm shadow-md">
          {avatarUrl ? (
            <img src={avatarUrl} alt={username} />
          ) : (
            username.charAt(0).toUpperCase()
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold truncate text-[var(--text-primary)]">
            {displayName || username}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-[11px] text-[var(--text-muted)]">@{username}</span>
            <span className="text-[10px] text-amber-400 font-bold bg-amber-400/10 px-1.5 py-0.5 rounded flex items-center">
              <Star className="w-2.5 h-2.5 inline mr-0.5" /> {karmaScore}
            </span>
          </div>
        </div>
        {currentUserId !== id && (
          <button
            onClick={handleFollowClick}
            disabled={loading}
            className={`text-[11px] px-3 py-1.5 rounded-lg font-semibold transition-all ${
              isFollowing
                ? "bg-white/10 text-[var(--text-primary)] hover:bg-white/20 border border-[var(--border-subtle)]"
                : "bg-[var(--accent-violet)] text-white hover:brightness-110 shadow-[0_2px_8px_rgba(139,92,246,0.3)]"
            }`}
          >
            {isFollowing ? "Following" : "Follow"}
          </button>
        )}
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card glass-card-hover p-6"
    >
      <div className="flex items-start gap-4">
        <div className="avatar avatar-lg shadow-lg shadow-violet-500/20">
          {avatarUrl ? (
            <img src={avatarUrl} alt={username} />
          ) : (
            username.charAt(0).toUpperCase()
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-bold text-lg text-[var(--text-primary)] truncate tracking-tight">
              {displayName || username}
            </h3>
            {badges.length > 0 && (
              <div className="flex items-center gap-1 bg-white/5 px-2 py-0.5 rounded-md border border-[var(--border-subtle)]">
                {badges.slice(0, 3).map((badge) => (
                  <span key={badge} className="text-[13px]" title={badge}>
                    {badge === "first_post" ? "🌱" : badge === "serial_builder" ? "🏗️" : badge === "karma_100" ? "⚡" : badge === "karma_500" ? "🚀" : "👍"}
                  </span>
                ))}
              </div>
            )}
          </div>
          <p className="text-[13px] text-[var(--accent-violet)] font-semibold mb-2.5">@{username}</p>
          {bio && (
            <p className="text-sm text-[var(--text-secondary)] line-clamp-2 mb-4 leading-relaxed">{bio}</p>
          )}

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5 text-xs bg-amber-400/10 px-2.5 py-1 rounded-md border border-amber-400/20">
              <Star className="w-3.5 h-3.5 text-amber-400 drop-shadow-[0_0_5px_rgba(251,191,36,0.5)]" />
              <span className="font-extrabold text-amber-400">{karmaScore}</span>
              <span className="text-[var(--text-muted)] font-medium">karma</span>
            </div>
            {localFollowerCount > 0 && (
              <div className="flex items-center gap-1.5 text-xs bg-cyan-400/10 px-2.5 py-1 rounded-md border border-cyan-400/20">
                <Users2 className="w-3.5 h-3.5 text-cyan-400 drop-shadow-[0_0_5px_rgba(6,182,212,0.5)]" />
                <span className="font-extrabold text-cyan-400">{localFollowerCount}</span>
                <span className="text-[var(--text-muted)] font-medium">followers</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3 mt-5 pt-4 border-t border-[var(--border-subtle)]">
        {currentUserId !== id && (
          <button
            onClick={handleFollowClick}
            disabled={loading}
            className={`text-sm py-2 px-5 flex-1 font-semibold transition-all ${
              isFollowing 
                ? "bg-white/5 text-[var(--text-primary)] rounded-lg hover:bg-white/10 border border-[var(--border-subtle)]" 
                : "btn-primary shadow-[0_2px_12px_rgba(139,92,246,0.25)]"
            }`}
          >
            {isFollowing ? "Following" : "Follow"}
          </button>
        )}
        {onMessage && (
          <button
            onClick={() => onMessage(id)}
            className="btn-ghost text-sm py-2 px-5 flex-1 font-semibold"
          >
            Message
          </button>
        )}
        <a
          href={`/arena/profile/${username}`}
          className="btn-icon"
          title="View profile"
        >
          <ExternalLink className="w-4 h-4" />
        </a>
      </div>
    </motion.div>
  );
}
