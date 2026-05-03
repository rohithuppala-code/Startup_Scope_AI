"use client";
import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  MessageCircle,
  Plus,
  Loader2,
  UserPlus,
  Users2,
  X,
  ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";
import ChatTimeline from "../components/ChatTimeline";

interface SearchProfile {
  id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
  karma_score: number;
}

interface Conversation {
  channel_id: string;
  participant_id: string;
  participant_username: string;
  participant_avatar: string | null;
  last_message: string | null;
  last_message_at: string | null;
}

export default function MessagesPage() {
  const userId = useUserStore((s) => s.userId);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [showNewDM, setShowNewDM] = useState(false);
  const [newDMUsername, setNewDMUsername] = useState("");
  const [searchResults, setSearchResults] = useState<SearchProfile[]>([]);
  const [searching, setSearching] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // Debounced search for founders
  useEffect(() => {
    if (!newDMUsername.trim() || !showNewDM) {
      setTimeout(() => setSearchResults([]), 0);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await api<SearchProfile[]>(
          `/api/v1/arena/search?q=${encodeURIComponent(newDMUsername.trim())}&type=profiles`
        );
        setSearchResults(data);
      } catch (err) {
        console.error(err);
      } finally {
        setSearching(false);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [newDMUsername, showNewDM]);

  useEffect(() => {
    if (!userId) return;
    api<Conversation[]>("/api/v1/messages/conversations", { userId })
      .then(setConversations)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [userId]);

  const filteredConversations = conversations.filter((c) =>
    c.participant_username?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const initNewDM = useCallback(async (profile: SearchProfile) => {
    if (!userId) return;
    try {
      // Init DM channel
      const res = await api<{ channel_id: string }>("/api/v1/messages/dm", {
        method: "POST",
        userId,
        body: { recipient_id: profile.id },
      });

      const newConv: Conversation = {
        channel_id: res.channel_id,
        participant_id: profile.id,
        participant_username: profile.username,
        participant_avatar: profile.avatar_url,
        last_message: null,
        last_message_at: null,
      };

      setConversations((prev) => {
        // If already exists, just select it
        const exists = prev.find(c => c.participant_id === profile.id);
        if (exists) return prev;
        return [newConv, ...prev];
      });
      setSelectedConv(newConv);
      setShowNewDM(false);
      setNewDMUsername("");
      setSearchResults([]);
      setIsSidebarOpen(false);
    } catch (err) {
      console.error("[Messages] Init DM error:", err);
    }
  }, [userId]);

  return (
    <div className="flex h-full bg-[var(--bg-primary)]">
      {/* ─── Conversations List ─── */}
      <div
        className={`w-full md:w-[360px] shrink-0 border-r border-[var(--border-subtle)] flex flex-col bg-black/10 backdrop-blur-sm z-10 ${
          !isSidebarOpen ? "hidden" : "flex"
        }`}
      >
        {/* Header */}
        <div className="px-5 py-5 border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)]/50">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold text-[var(--text-primary)] tracking-tight">Messages</h2>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowNewDM(!showNewDM)}
              className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all ${showNewDM ? "bg-[var(--accent-violet)] text-white shadow-md shadow-violet-500/20" : "bg-white/5 border border-[var(--border-subtle)] text-[var(--text-muted)] hover:bg-white/10 hover:text-[var(--text-primary)]"}`}
            >
              {showNewDM ? (
                <X className="w-4 h-4" />
              ) : (
                <Plus className="w-5 h-5" />
              )}
            </motion.button>
          </div>

          {/* New DM Input */}
          <AnimatePresence>
            {showNewDM && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="mb-4 overflow-visible"
              >
                <div className="relative">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newDMUsername}
                      onChange={(e) => setNewDMUsername(e.target.value)}
                      placeholder="Search founders by name..."
                      className="input-dark py-2.5 flex-1 text-sm shadow-inner"
                      autoFocus
                    />
                  </div>
                  {/* Search Results Dropdown */}
                  {(searchResults.length > 0 || searching) && (
                    <div className="absolute top-full left-0 right-0 mt-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-xl shadow-2xl overflow-hidden z-50 max-h-60 overflow-y-auto glow-border">
                      {searching ? (
                        <div className="p-4 flex justify-center">
                          <Loader2 className="w-5 h-5 animate-spin text-[var(--accent-violet)]" />
                        </div>
                      ) : (
                        searchResults.map((p) => (
                          <button
                            key={p.id}
                            onClick={() => initNewDM(p)}
                            className="w-full flex items-center gap-3 p-3 text-left hover:bg-white/[0.05] transition-colors border-b border-[var(--border-subtle)] last:border-b-0"
                          >
                            <div className="avatar avatar-sm shrink-0 shadow-sm">
                              {p.avatar_url ? <img src={p.avatar_url} alt="" /> : p.username.charAt(0).toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{p.display_name || p.username}</p>
                              <p className="text-[11px] font-medium text-[var(--text-muted)] truncate">@{p.username} • <span className="text-amber-400 font-bold">⚡{p.karma_score}</span></p>
                            </div>
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="flex justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-[var(--accent-violet)]" />
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="text-center py-16 px-5 glass-card m-3 border-dashed">
              <MessageCircle className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3 opacity-50" />
              <p className="text-[15px] font-semibold text-[var(--text-primary)] tracking-tight">No conversations yet</p>
              <p className="text-xs font-medium text-[var(--text-muted)] mt-1.5 leading-relaxed">
                Start a new DM by clicking the <strong className="text-[var(--text-secondary)]">+</strong> button above
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {filteredConversations.map((conv) => {
                const isActive = selectedConv?.channel_id === conv.channel_id;
                return (
                  <motion.button
                    key={conv.channel_id}
                    whileHover={{ x: 2 }}
                    onClick={() => {
                      setSelectedConv(conv);
                      setIsSidebarOpen(false);
                    }}
                    className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-xl text-left transition-all ${
                      isActive
                        ? "bg-[var(--accent-violet)]/10 shadow-[inset_2px_0_0_0_rgba(139,92,246,1)]"
                        : "hover:bg-white/[0.04] border border-transparent hover:border-[var(--border-subtle)]"
                    }`}
                  >
                    <div className="avatar avatar-md shadow-sm">
                      {conv.participant_avatar ? (
                        <img src={conv.participant_avatar} alt="" />
                      ) : (
                        conv.participant_username.charAt(0).toUpperCase()
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-[15px] truncate tracking-tight mb-0.5 ${isActive ? "font-bold text-[var(--text-primary)]" : "font-semibold text-[var(--text-secondary)]"}`}>
                        {conv.participant_username}
                      </p>
                      <p className={`text-[13px] truncate ${isActive ? "text-[var(--text-secondary)]" : "text-[var(--text-muted)]"}`}>
                        {conv.last_message || <span className="italic opacity-50">No messages yet</span>}
                      </p>
                    </div>
                    {conv.last_message_at && (
                      <span className="text-[11px] font-medium text-[var(--text-muted)] shrink-0 bg-white/5 px-2 py-1 rounded-md">
                        {new Date(conv.last_message_at).toLocaleDateString()}
                      </span>
                    )}
                  </motion.button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ─── Chat View ─── */}
      <div
        className={`relative flex-1 min-w-0 ${
          isSidebarOpen ? "hidden md:flex" : "flex"
        } flex-col bg-[var(--bg-primary)]`}
      >
        {!isSidebarOpen && (
          <button 
            onClick={() => setIsSidebarOpen(true)}
            className="absolute left-0 top-1/2 -translate-y-1/2 z-50 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] border-l-0 p-2 rounded-r-xl shadow-lg hover:bg-white/5 transition-colors group"
          >
            <ChevronRight className="w-5 h-5 text-[var(--text-primary)] group-hover:scale-110 transition-transform" />
          </button>
        )}
        {selectedConv ? (
          <ChatTimeline
            channelId={selectedConv.channel_id}
            participantName={selectedConv.participant_username}
            participantAvatar={selectedConv.participant_avatar}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full">
            <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mb-6 border border-[var(--border-subtle)] shadow-xl shadow-violet-500/5">
              <MessageCircle className="w-10 h-10 text-[var(--text-muted)]" />
            </div>
            <h3 className="text-xl font-bold text-[var(--text-primary)] mb-2 tracking-tight">
              Your Messages
            </h3>
            <p className="text-base text-[var(--text-secondary)] max-w-sm text-center leading-relaxed">
              Select a conversation from the sidebar or start a new DM to chat with founders and share ideas.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
