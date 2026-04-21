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
        whileHover={{ x: 2 }}
        className="flex items-center gap-2.5 p-2 rounded-lg hover:bg-white/[0.02] transition-colors cursor-pointer"
      >
        <div className="avatar avatar-sm">
          {avatarUrl ? (
            <img src={avatarUrl} alt={username} />
          ) : (
            username.charAt(0).toUpperCase()
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate text-[var(--text-primary)]">
            {displayName || username}
          </p>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-[var(--text-muted)]">@{username}</span>
            <span className="text-[10px] text-amber-400 font-medium">
              <Star className="w-2.5 h-2.5 inline" /> {karmaScore}
            </span>
          </div>
        </div>
        {currentUserId !== id && (
          <button
            onClick={handleFollowClick}
            disabled={loading}
            className={`text-[10px] px-2.5 py-1 rounded-lg font-medium transition-colors ${
              isFollowing
                ? "bg-white/5 text-[var(--text-secondary)] hover:bg-white/10"
                : "bg-[var(--accent-violet)]/10 text-[var(--accent-violet)] hover:bg-[var(--accent-violet)]/20"
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
      className="glass-card glass-card-hover p-5"
    >
      <div className="flex items-start gap-4">
        <div className="avatar avatar-lg">
          {avatarUrl ? (
            <img src={avatarUrl} alt={username} />
          ) : (
            username.charAt(0).toUpperCase()
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <h3 className="font-semibold text-base text-[var(--text-primary)] truncate">
              {displayName || username}
            </h3>
            {badges.length > 0 && (
              <div className="flex items-center gap-0.5">
                {badges.slice(0, 3).map((badge) => (
                  <span key={badge} className="text-xs" title={badge}>
                    {badge === "first_post" ? "🌱" : badge === "serial_builder" ? "🏗️" : badge === "karma_100" ? "⚡" : badge === "karma_500" ? "🚀" : "👍"}
                  </span>
                ))}
              </div>
            )}
          </div>
          <p className="text-xs text-[var(--accent-violet)] font-medium mb-1.5">@{username}</p>
          {bio && (
            <p className="text-sm text-[var(--text-secondary)] line-clamp-2 mb-3">{bio}</p>
          )}

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1 text-xs">
              <Star className="w-3 h-3 text-amber-400" />
              <span className="font-bold text-amber-400">{karmaScore}</span>
              <span className="text-[var(--text-muted)]">karma</span>
            </div>
            {localFollowerCount > 0 && (
              <div className="flex items-center gap-1 text-xs">
                <Users2 className="w-3 h-3 text-cyan-400" />
                <span className="font-bold text-cyan-400">{localFollowerCount}</span>
                <span className="text-[var(--text-muted)]">followers</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 mt-4 pt-3 border-t border-[var(--border-subtle)]">
        {currentUserId !== id && (
          <button
            onClick={handleFollowClick}
            disabled={loading}
            className={`text-xs py-2 px-4 flex-1 transition-colors ${
              isFollowing ? "bg-white/5 text-[var(--text-secondary)] rounded-lg hover:bg-white/10" : "btn-primary"
            }`}
          >
            {isFollowing ? "Following" : "Follow"}
          </button>
        )}
        {onMessage && (
          <button
            onClick={() => onMessage(id)}
            className="btn-ghost text-xs py-2 px-4 flex-1"
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
