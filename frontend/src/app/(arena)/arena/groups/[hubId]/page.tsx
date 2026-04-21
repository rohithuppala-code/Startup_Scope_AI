"use client";
import { useState, useEffect, use } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Hash,
  Users2,
  Plus,
  X,
  ArrowLeft,
  Loader2,
  Star,
} from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";
import ChatTimeline from "../../components/ChatTimeline";

interface Channel {
  id: string;
  name: string;
  kind: string;
  description: string | null;
}

interface HubMember {
  user_id: string;
  username: string;
  karma_score: number;
}

export default function GroupDetailPage({
  params,
}: {
  params: Promise<{ hubId: string }>;
}) {
  const { hubId } = use(params);
  const userId = useUserStore((s) => s.userId);
  const [hubName, setHubName] = useState("Loading...");
  const [channels, setChannels] = useState<Channel[]>([]);
  const [members, setMembers] = useState<HubMember[]>([]);
  const [activeChannel, setActiveChannel] = useState<Channel | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCreateChannel, setShowCreateChannel] = useState(false);
  const [newChannelName, setNewChannelName] = useState("");
  const [creatingChannel, setCreatingChannel] = useState(false);

  // Load hub info, channels, and members
  useEffect(() => {
    const loadAll = async () => {
      try {
        const [hubRes, chRes, memRes] = await Promise.all([
          api<{ name: string }>(`/api/v1/hubs/${hubId}`).catch(() => ({ name: "Group" })),
          api<Channel[]>(`/api/v1/hubs/${hubId}/channels`).catch(() => []),
          api<HubMember[]>(`/api/v1/hubs/${hubId}/members`).catch(() => []),
        ]);
        setHubName(hubRes.name);
        setChannels(chRes as Channel[]);
        setMembers(memRes as HubMember[]);
        // Auto-select first channel
        if ((chRes as Channel[]).length > 0) {
          setActiveChannel((chRes as Channel[])[0]);
        }
      } catch (err) {
        console.error("[GroupDetail] Load error:", err);
      } finally {
        setLoading(false);
      }
    };
    loadAll();
  }, [hubId]);

  const createChannel = async () => {
    if (!newChannelName.trim() || !userId || creatingChannel) return;
    setCreatingChannel(true);
    try {
      const ch = await api<Channel>(
        `/api/v1/hubs/${hubId}/channels`,
        {
          method: "POST",
          userId,
          body: { name: newChannelName.trim().toLowerCase().replace(/\s+/g, "-"), kind: "text", description: "" },
        }
      );
      setChannels((prev) => [...prev, ch]);
      setActiveChannel(ch);
      setNewChannelName("");
      setShowCreateChannel(false);
    } catch (err) {
      console.error("[GroupDetail] Channel create error:", err);
    } finally {
      setCreatingChannel(false);
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
    <div className="flex h-full">
      {/* Left: Channels + Members Sidebar */}
      <div className="w-[220px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)]/30 flex flex-col">
        {/* Hub Header */}
        <div className="px-3 py-3 border-b border-[var(--border-subtle)]">
          <Link
            href="/arena/groups"
            className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] mb-2"
          >
            <ArrowLeft className="w-3 h-3" />
            Groups
          </Link>
          <h2 className="text-sm font-bold text-[var(--text-primary)] truncate">{hubName}</h2>
          <p className="text-[10px] text-[var(--text-muted)]">{members.length} members · {channels.length} channels</p>
        </div>

        {/* Channels */}
        <div className="flex-1 overflow-y-auto px-2 py-2">
          <div className="flex items-center justify-between px-1 mb-1">
            <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">Channels</span>
            <button onClick={() => setShowCreateChannel(true)} className="btn-icon !w-5 !h-5" title="Create channel">
              <Plus className="w-3 h-3" />
            </button>
          </div>

          {/* Create Channel Inline */}
          <AnimatePresence>
            {showCreateChannel && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden mb-1"
              >
                <div className="p-2 rounded-lg bg-[var(--bg-glass)] border border-[var(--border-subtle)]">
                  <input
                    type="text"
                    value={newChannelName}
                    onChange={(e) => setNewChannelName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && createChannel()}
                    placeholder="channel-name"
                    className="input-dark text-xs py-1.5 mb-1.5"
                    autoFocus
                  />
                  <div className="flex gap-1">
                    <button
                      onClick={createChannel}
                      disabled={!newChannelName.trim() || creatingChannel}
                      className="btn-primary text-[10px] py-1 px-2 flex-1 disabled:opacity-50"
                    >
                      {creatingChannel ? "..." : "Create"}
                    </button>
                    <button
                      onClick={() => { setShowCreateChannel(false); setNewChannelName(""); }}
                      className="btn-ghost text-[10px] py-1 px-2"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {channels.map((ch) => (
            <button
              key={ch.id}
              onClick={() => setActiveChannel(ch)}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-colors mb-0.5 ${
                activeChannel?.id === ch.id
                  ? "bg-[var(--accent-violet)]/10 text-[var(--accent-violet)] font-medium"
                  : "text-[var(--text-secondary)] hover:bg-white/[0.02] hover:text-[var(--text-primary)]"
              }`}
            >
              <Hash className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">{ch.name}</span>
            </button>
          ))}

          {channels.length === 0 && !showCreateChannel && (
            <p className="text-[10px] text-[var(--text-muted)] px-2 py-3 text-center">
              No channels yet.
              <button onClick={() => setShowCreateChannel(true)} className="text-[var(--accent-violet)] hover:underline ml-1">Create one</button>
            </p>
          )}
        </div>

        {/* Members */}
        <div className="border-t border-[var(--border-subtle)] px-2 py-2">
          <span className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider px-1 block mb-1">
            Members ({members.length})
          </span>
          <div className="max-h-[120px] overflow-y-auto space-y-0.5">
            {members.slice(0, 10).map((m) => (
              <div key={m.user_id} className="flex items-center gap-2 px-1 py-1 rounded text-xs">
                <div className="avatar" style={{ width: 20, height: 20, fontSize: 9 }}>
                  {m.username.charAt(0).toUpperCase()}
                </div>
                <span className="text-[var(--text-secondary)] truncate flex-1">{m.username}</span>
                <span className="text-[10px] text-amber-400 flex items-center gap-0.5">
                  <Star className="w-2.5 h-2.5" />
                  {m.karma_score || 0}
                </span>
              </div>
            ))}
            {members.length === 0 && (
              <p className="text-[10px] text-[var(--text-muted)] text-center py-2">No members yet</p>
            )}
          </div>
        </div>
      </div>

      {/* Right: Chat Area */}
      <div className="flex-1 min-w-0">
        {activeChannel ? (
          <ChatTimeline
            channelId={activeChannel.id}
            participantName={`#${activeChannel.name}`}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mb-3 border border-[var(--border-subtle)]">
              <Hash className="w-6 h-6 text-[var(--text-muted)]" />
            </div>
            <p className="text-sm text-[var(--text-secondary)] mb-1">No channel selected</p>
            <p className="text-xs text-[var(--text-muted)]">
              {channels.length === 0 ? "Create a channel to get started" : "Select a channel from the sidebar"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
