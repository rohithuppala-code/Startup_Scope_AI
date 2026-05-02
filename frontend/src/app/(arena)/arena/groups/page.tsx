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
    <div className="max-w-4xl mx-auto px-5 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold gradient-text tracking-tight mb-2">Groups</h1>
          <p className="text-[15px] font-medium text-[var(--text-secondary)] leading-relaxed">
            Join founder communities and collaborate on ideas.
          </p>
        </div>
        <motion.button
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          onClick={() => setShowCreateModal(true)}
          className="btn-primary text-sm py-2.5 px-5 flex items-center gap-2 font-semibold shadow-md shadow-violet-500/20"
        >
          <Plus className="w-4 h-4" />
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md px-4"
            onClick={() => setShowCreateModal(false)}
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 10 }}
              onClick={(e) => e.stopPropagation()}
              className="glass-card noise-overlay p-8 w-full max-w-md shadow-2xl border-violet-500/30"
            >
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">Create Group</h3>
                <button
                  onClick={() => setShowCreateModal(false)}
                  className="p-1.5 rounded-lg hover:bg-white/10 transition-colors"
                >
                  <X className="w-5 h-5 text-[var(--text-muted)]" />
                </button>
              </div>

              <div className="space-y-5">
                <div>
                  <label className="block text-sm font-semibold text-[var(--text-secondary)] mb-2">
                    Group Name
                  </label>
                  <input
                    type="text"
                    value={newGroupName}
                    onChange={(e) => setNewGroupName(e.target.value)}
                    placeholder="e.g. SaaS Builders, Deep Tech..."
                    className="input-dark py-3"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-[var(--text-secondary)] mb-2">
                    Description
                  </label>
                  <textarea
                    value={newGroupDescription}
                    onChange={(e) => setNewGroupDescription(e.target.value)}
                    placeholder="What's this group about?"
                    className="input-dark py-3 resize-y"
                    rows={3}
                  />
                </div>
                <div className="flex gap-3 pt-4">
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={createGroup}
                    disabled={!newGroupName.trim() || creating}
                    className="btn-primary py-3 flex-1 flex items-center justify-center gap-2 font-semibold shadow-md disabled:opacity-50"
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
                    className="btn-ghost py-3 flex-1 font-semibold border-transparent hover:bg-white/5"
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
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass-card p-6 animate-pulse">
              <div className="skeleton h-14 w-14 rounded-2xl mb-4" />
              <div className="skeleton h-6 w-48 mb-3" />
              <div className="skeleton h-3 w-full mb-1.5" />
              <div className="skeleton h-3 w-2/3" />
            </div>
          ))}
        </div>
      ) : hubs.length === 0 ? (
        <div className="text-center py-24">
          <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mx-auto mb-6 border border-[var(--border-subtle)] shadow-xl shadow-violet-500/5">
            <Users2 className="w-10 h-10 text-[var(--text-muted)]" />
          </div>
          <h3 className="text-xl font-bold text-[var(--text-primary)] mb-2 tracking-tight">
            No groups yet
          </h3>
          <p className="text-base text-[var(--text-secondary)] mb-6">
            Be the first to create a founder community!
          </p>
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => setShowCreateModal(true)}
            className="btn-primary text-base py-3 px-6 font-semibold shadow-md"
          >
            <Plus className="w-5 h-5 inline mr-2" />
            Create First Group
          </motion.button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {hubs.map((hub, i) => (
            <motion.div
              key={hub.id}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="glass-card glass-card-hover p-6 border-[var(--border-subtle)] hover:border-violet-500/30"
            >
              <div className="flex items-start gap-5">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-600 via-purple-500 to-cyan-500 flex items-center justify-center text-2xl font-bold text-white shrink-0 shadow-lg shadow-violet-500/25">
                  {hub.icon_url ? (
                    <img src={hub.icon_url} alt="" className="w-full h-full object-cover rounded-2xl" />
                  ) : (
                    hub.name.charAt(0).toUpperCase()
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-lg text-[var(--text-primary)] mb-1.5 tracking-tight truncate">
                    {hub.name}
                  </h3>
                  {hub.description && (
                    <p className="text-sm text-[var(--text-secondary)] line-clamp-2 mb-4 leading-relaxed">
                      {hub.description}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-[13px] font-medium text-[var(--text-muted)]">
                    <span className="flex items-center gap-1.5 bg-white/5 px-2 py-1 rounded-md">
                      <Users2 className="w-4 h-4 text-[var(--accent-violet)]" />
                      {hub.member_count} members
                    </span>
                    <span className="flex items-center gap-1.5 bg-white/5 px-2 py-1 rounded-md">
                      <Hash className="w-4 h-4 text-cyan-400" />
                      {hub.channel_count} channels
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3 mt-6 pt-4 border-t border-[var(--border-subtle)]">
                <motion.button
                  whileHover={joinedHubs.has(hub.id) ? {} : { scale: 1.02 }}
                  whileTap={joinedHubs.has(hub.id) ? {} : { scale: 0.98 }}
                  onClick={() => !joinedHubs.has(hub.id) && joinHub(hub.id)}
                  disabled={joinedHubs.has(hub.id)}
                  className={`text-sm font-semibold py-2.5 px-5 flex-1 transition-all ${
                    joinedHubs.has(hub.id) 
                      ? "bg-[var(--accent-violet)]/10 text-[var(--accent-violet)] border border-[var(--accent-violet)]/20 rounded-xl cursor-default" 
                      : "btn-primary shadow-[0_2px_12px_rgba(139,92,246,0.25)]"
                  }`}
                >
                  {joinedHubs.has(hub.id) ? "Joined" : "Join Group"}
                </motion.button>
                <Link
                  href={`/arena/groups/${hub.id}`}
                  className="btn-ghost text-sm font-semibold py-2.5 px-5 flex items-center justify-center gap-2 flex-1 border-transparent bg-white/5 hover:bg-white/10"
                >
                  Open
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
