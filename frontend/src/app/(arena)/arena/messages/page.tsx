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
    c.participant_username.toLowerCase().includes(searchQuery.toLowerCase())
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
    } catch (err) {
      console.error("[Messages] Init DM error:", err);
    }
  }, [userId]);

  return (
    <div className="flex h-full">
      {/* ─── Conversations List ─── */}
      <div
        className={`w-full md:w-[320px] shrink-0 border-r border-[var(--border-subtle)] flex flex-col ${
          selectedConv ? "hidden md:flex" : "flex"
        }`}
      >
        {/* Header */}
        <div className="px-4 py-4 border-b border-[var(--border-subtle)]">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-bold text-[var(--text-primary)]">Messages</h2>
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={() => setShowNewDM(!showNewDM)}
              className="btn-icon"
            >
              {showNewDM ? (
                <span className="text-xs font-bold">✕</span>
              ) : (
                <Plus className="w-4 h-4" />
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
                className="overflow-hidden mb-3"
              >
                <div className="relative">
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={newDMUsername}
                      onChange={(e) => setNewDMUsername(e.target.value)}
                      placeholder="Search founders by name..."
                      className="input-dark text-sm py-2 flex-1"
                      autoFocus
                    />
                  </div>
                  {/* Search Results Dropdown */}
                  {(searchResults.length > 0 || searching) && (
                    <div className="absolute top-full left-0 right-0 mt-1 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg shadow-xl overflow-hidden z-50 max-h-60 overflow-y-auto">
                      {searching ? (
                        <div className="p-3 flex justify-center">
                          <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-violet)]" />
                        </div>
                      ) : (
                        searchResults.map((p) => (
                          <button
                            key={p.id}
                            onClick={() => initNewDM(p)}
                            className="w-full flex items-center gap-3 p-3 text-left hover:bg-white/[0.05] transition-colors border-b border-[var(--border-subtle)] last:border-b-0"
                          >
                            <div className="avatar avatar-sm shrink-0">
                              {p.avatar_url ? <img src={p.avatar_url} alt="" /> : p.username.charAt(0).toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-[var(--text-primary)] truncate">{p.display_name || p.username}</p>
                              <p className="text-[10px] text-[var(--text-muted)] truncate">@{p.username} • ⚡{p.karma_score}</p>
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

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search conversations..."
              className="input-dark text-sm py-2 pl-9"
            />
          </div>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-[var(--accent-violet)]" />
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="text-center py-12 px-4">
              <MessageCircle className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-2" />
              <p className="text-sm text-[var(--text-secondary)]">No conversations yet</p>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                Start a new DM by clicking the + button
              </p>
            </div>
          ) : (
            <div className="py-1">
              {filteredConversations.map((conv) => {
                const isActive = selectedConv?.channel_id === conv.channel_id;
                return (
                  <motion.button
                    key={conv.channel_id}
                    whileHover={{ x: 2 }}
                    onClick={() => setSelectedConv(conv)}
                    className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
                      isActive
                        ? "bg-[var(--accent-violet)]/8 border-l-2 border-[var(--accent-violet)]"
                        : "hover:bg-white/[0.02]"
                    }`}
                  >
                    <div className="avatar avatar-sm">
                      {conv.participant_avatar ? (
                        <img src={conv.participant_avatar} alt="" />
                      ) : (
                        conv.participant_username.charAt(0).toUpperCase()
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                        {conv.participant_username}
                      </p>
                      <p className="text-xs text-[var(--text-muted)] truncate">
                        {conv.last_message || "No messages yet"}
                      </p>
                    </div>
                    {conv.last_message_at && (
                      <span className="text-[10px] text-[var(--text-muted)] shrink-0">
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
        className={`flex-1 min-w-0 ${
          !selectedConv ? "hidden md:flex" : "flex"
        } flex-col`}
      >
        {selectedConv ? (
          <ChatTimeline
            channelId={selectedConv.channel_id}
            participantName={selectedConv.participant_username}
            participantAvatar={selectedConv.participant_avatar}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-full">
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-violet-500/10 to-emerald-500/10 flex items-center justify-center mb-4 border border-[var(--border-subtle)]">
              <MessageCircle className="w-8 h-8 text-[var(--text-muted)]" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--text-primary)] mb-1">
              Your Messages
            </h3>
            <p className="text-sm text-[var(--text-secondary)] max-w-xs text-center">
              Select a conversation or start a new DM to chat with founders and share ideas.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
