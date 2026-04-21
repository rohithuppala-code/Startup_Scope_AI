"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import {
  Users2,
  Hash,
  Plus,
  Loader2,
  ArrowRight,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";

interface Hub {
  id: string;
  name: string;
  description: string | null;
  icon_url: string | null;
  member_count: number;
  channel_count: number;
}

export default function GroupsPage() {
  const userId = useUserStore((s) => s.userId);
  const [hubs, setHubs] = useState<Hub[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDescription, setNewGroupDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [joinedHubs, setJoinedHubs] = useState<Set<string>>(new Set());

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [hubsData, joinedData] = await Promise.all([
          api<Hub[]>("/api/v1/hubs"),
          userId ? api<string[]>("/api/v1/hubs/joined", { userId }) : Promise.resolve([])
        ]);
        setHubs(hubsData);
        setJoinedHubs(new Set(joinedData));
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [userId]);

  const joinHub = async (hubId: string) => {
    if (!userId) return;
    try {
      await api<{ message: string; already_member: boolean }>(`/api/v1/hubs/${hubId}/join`, { method: "POST", userId });
      setJoinedHubs((prev) => {
        const next = new Set(prev);
        next.add(hubId);
        return next;
      });
      setHubs((prev) =>
        prev.map((h) =>
          h.id === hubId ? { ...h, member_count: h.member_count + 1 } : h
        )
      );
    } catch (err) {
      console.error("[Groups] Join error:", err);
    }
  };

  const createGroup = async () => {
    if (!newGroupName.trim() || !userId || creating) return;
    setCreating(true);
    try {
      const hub = await api<Hub>(
        `/api/v1/hubs?name=${encodeURIComponent(newGroupName.trim())}&description=${encodeURIComponent(newGroupDescription.trim())}`,
        { method: "POST", userId }
      );
      setHubs((prev) => [hub, ...prev]);
      setShowCreateModal(false);
      setNewGroupName("");
      setNewGroupDescription("");
    } catch (err) {
      console.error("[Groups] Create error:", err);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold gradient-text">Groups</h1>
          <p className="text-sm text-[var(--text-secondary)] mt-0.5">
            Join founder communities and collaborate on ideas
          </p>
        </div>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => setShowCreateModal(true)}
          className="btn-primary text-xs flex items-center gap-1.5"
        >
          <Plus className="w-3.5 h-3.5" />
          Create Group
        </motion.button>
      </div>

      {/* Create Group Modal */}
      <AnimatePresence>
        {showCreateModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm px-4"
            onClick={() => setShowCreateModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-card p-6 w-full max-w-md glow-border"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-[var(--text-primary)]">Create Group</h3>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="btn-icon"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                    Group Name
                  </label>
                  <input
                    type="text"
                    value={newGroupName}
                    onChange={(e) => setNewGroupName(e.target.value)}
                    placeholder="e.g. SaaS Builders, Deep Tech..."
                    className="input-dark"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                    Description
                  </label>
                  <textarea
                    value={newGroupDescription}
                    onChange={(e) => setNewGroupDescription(e.target.value)}
                    placeholder="What's this group about?"
                    className="input-dark"
                    rows={3}
                  />
                </div>
                <div className="flex gap-2 pt-2">
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={createGroup}
                    disabled={!newGroupName.trim() || creating}
                    className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {creating ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <>
                        <Plus className="w-4 h-4" />
                        Create
                      </>
                    )}
                  </motion.button>
                  <button
                    onClick={() => setShowCreateModal(false)}
                    className="btn-ghost flex-1"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Groups Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass-card p-6 animate-pulse">
              <div className="skeleton h-12 w-12 rounded-xl mb-3" />
              <div className="skeleton h-5 w-40 mb-2" />
              <div className="skeleton h-3 w-full mb-1" />
              <div className="skeleton h-3 w-2/3" />
            </div>
          ))}
        </div>
      ) : hubs.length === 0 ? (
        <div className="text-center py-20">
          <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mx-auto mb-4 border border-[var(--border-subtle)]">
            <Users2 className="w-8 h-8 text-[var(--text-muted)]" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-1">
            No groups yet
          </h3>
          <p className="text-sm text-[var(--text-secondary)] mb-4">
            Be the first to create a founder community!
          </p>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowCreateModal(true)}
            className="btn-primary text-sm"
          >
            <Plus className="w-4 h-4 inline mr-1" />
            Create First Group
          </motion.button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {hubs.map((hub, i) => (
            <motion.div
              key={hub.id}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="glass-card glass-card-hover p-5"
            >
              <div className="flex items-start gap-4">
                <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center text-xl font-bold text-white shrink-0 shadow-lg shadow-violet-500/20">
                  {hub.icon_url ? (
                    <img src={hub.icon_url} alt="" className="w-full h-full object-cover rounded-xl" />
                  ) : (
                    hub.name.charAt(0).toUpperCase()
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-base text-[var(--text-primary)] mb-1">
                    {hub.name}
                  </h3>
                  {hub.description && (
                    <p className="text-xs text-[var(--text-secondary)] line-clamp-2 mb-3">
                      {hub.description}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-[var(--text-muted)]">
                    <span className="flex items-center gap-1">
                      <Users2 className="w-3 h-3" />
                      {hub.member_count} members
                    </span>
                    <span className="flex items-center gap-1">
                      <Hash className="w-3 h-3" />
                      {hub.channel_count} channels
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 mt-4 pt-3 border-t border-[var(--border-subtle)]">
                <motion.button
                  whileHover={joinedHubs.has(hub.id) ? {} : { scale: 1.02 }}
                  whileTap={joinedHubs.has(hub.id) ? {} : { scale: 0.98 }}
                  onClick={() => !joinedHubs.has(hub.id) && joinHub(hub.id)}
                  disabled={joinedHubs.has(hub.id)}
                  className={`text-xs py-2 px-4 flex-1 transition-colors ${
                    joinedHubs.has(hub.id) 
                      ? "bg-[var(--accent-violet)]/20 text-[var(--accent-violet)] border border-[var(--accent-violet)]/30 rounded-lg cursor-default" 
                      : "btn-primary"
                  }`}
                >
                  {joinedHubs.has(hub.id) ? "Joined" : "Join Group"}
                </motion.button>
                <Link
                  href={`/arena/groups/${hub.id}`}
                  className="btn-ghost text-xs py-2 px-4 flex items-center gap-1"
                >
                  Open
                  <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
