"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Send,
  Plus,
  X,
  Zap,
  BarChart3,
  FileUp,
  Loader2,
  Sparkles,
  MessageSquare,
  FileIcon,
  Download,
  Smile,
} from "lucide-react";
import { useSupabaseRealtime } from "@/hooks/use-supabase-realtime";
import { useUserStore } from "@/stores/user-store";
import LiveIdeaCard from "./LiveIdeaCard";
import { GroupPollCard } from "./GroupPollCard";
import { api } from "@/lib/api";

interface ChatTimelineProps {
  channelId: string;
  participantName?: string;
  participantAvatar?: string | null;
}

export default function ChatTimeline({
  channelId,
  participantName = "Chat",
  participantAvatar,
}: ChatTimelineProps) {
  const userId = useUserStore((s) => s.userId);
  const { messages, sendMessage, isConnected } = useSupabaseRealtime(channelId);
  const [inputText, setInputText] = useState("");
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [showIdeaInput, setShowIdeaInput] = useState(false);
  const [ideaText, setIdeaText] = useState("");
  const [ideaMarket, setIdeaMarket] = useState("");
  const [ideaBudget, setIdeaBudget] = useState("");
  const [showPollCreator, setShowPollCreator] = useState(false);
  const [pollQuestion, setPollQuestion] = useState("");
  const [pollOptions, setPollOptions] = useState(["", ""]);
  const [submitting, setSubmitting] = useState(false);
  const [synthResult, setSynthResult] = useState<string | null>(null);
  const [synthLoading, setSynthLoading] = useState(false);
  const [replyTo, setReplyTo] = useState<{ id: string; content: string } | null>(null);
  const [activeReactionMsg, setActiveReactionMsg] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = useCallback(async () => {
    if (!inputText.trim() || !userId || !channelId) return;
    let text = inputText.trim();
    if (replyTo) {
      text = `↩ Reply to "${replyTo.content.slice(0, 50)}..."\n\n${text}`;
      setReplyTo(null);
    }
    setInputText("");
    try {
      await sendMessage(channelId, userId, text);
    } catch (err) {
      console.error("[ChatTimeline] Send error:", err);
      setInputText(text);
    }
  }, [inputText, userId, channelId, sendMessage, replyTo]);

  const handleShareIdea = useCallback(async () => {
    if (!ideaText.trim() || !userId || submitting) return;
    setSubmitting(true);
    try {
      // 1. Submit validation (async — returns immediately with validation_id)
      const valRes = await api<{ validation_id: string }>("/api/v1/validate", {
        method: "POST",
        userId,
        body: {
          idea_description: ideaText.trim(),
          target_market: ideaMarket.trim() || undefined,
          budget_constraints: ideaBudget.trim() || undefined,
        },
      });

      // 2. Immediately send the idea card to the chat with the validation_id
      //    The LiveIdeaCard will stream the AI results via WebSocket
      const payload = {
        validation_id: valRes.validation_id,
        post_id: null,  // will be published later when validation completes
        description: ideaText.trim()
      };
      const text = `[IDEA] ${JSON.stringify(payload)}`;
      await sendMessage(channelId, userId, text);

      setIdeaText("");
      setIdeaMarket("");
      setIdeaBudget("");
      setShowIdeaInput(false);
      setActionMenuOpen(false);
    } catch (err) {
      console.error("[ChatTimeline] Share idea error:", err);
    } finally {
      setSubmitting(false);
    }
  }, [ideaText, userId, channelId, sendMessage, submitting]);

    const handleCreatePoll = useCallback(async () => {
    if (!pollQuestion.trim() || !userId || submitting) return;
    const validOptions = pollOptions.filter((o) => o.trim());
    if (validOptions.length < 2) return;
    setSubmitting(true);
    try {
      const payload = {
        question: pollQuestion.trim(),
        options: validOptions
      };
      const text = `[POLL] ${JSON.stringify(payload)}`;
      await sendMessage(channelId, userId, text);
      setPollQuestion("");
      setPollOptions(["", ""]);
      setShowPollCreator(false);
      setActionMenuOpen(false);
    } catch (err) {
      console.error("[ChatTimeline] Poll error:", err);
    } finally {
      setSubmitting(false);
    }
  }, [pollQuestion, pollOptions, userId, channelId, sendMessage, submitting]);

    const handlePollVote = useCallback(async (messageId: string, optionIdx: number) => {
    if (!userId) return;
    try {
      const payload = { message_id: messageId, option_idx: optionIdx };
      const text = `[POLL_VOTE] ${JSON.stringify(payload)}`;
      await sendMessage(channelId, userId, text);
    } catch (err) {
      console.error("Vote failed:", err);
    }
  }, [userId, channelId, sendMessage]);

  const handleSynthesize = useCallback(async () => {
    if (synthLoading || messages.length === 0) return;
    if (synthResult) { setSynthResult(null); return; }
    setSynthLoading(true);
    try {
      // Find the most recent idea in the channel to synthesize
      const ideaMsg = [...messages].reverse().find(m => m.content.startsWith("[IDEA] "));
      if (ideaMsg) {
        const payload = JSON.parse(ideaMsg.content.slice(7));
        if (payload.post_id) {
          // Use the real AI synthesis endpoint
          const res = await api<{ summary: string; key_themes?: string[] }>(
            `/api/v1/arena/posts/${payload.post_id}/synthesize`,
            { method: "POST", userId: userId ?? undefined }
          );
          setSynthResult(res.summary || JSON.stringify(res, null, 2));
          return;
        }
      }
      // Fallback: summarize plain messages
      const recentContent = messages
        .filter(m => !m.content.startsWith("["))
        .slice(-15)
        .map(m => m.content)
        .join("\n");
      setSynthResult(`**Thread Summary** (${messages.length} messages)\n\n${recentContent.slice(0, 600)}${recentContent.length > 600 ? "..." : ""}`);
    } catch {
      setSynthResult("Synthesis unavailable. Make sure an idea has been validated and published.");
    } finally {
      setSynthLoading(false);
    }
  }, [messages, synthResult, synthLoading, userId]);

  const handleFileUpload = async (file: File) => {
    if (!userId || !channelId) return;
    setActionMenuOpen(false);
    setSubmitting(true);
    try {
      // Route through backend (uses service role key — bypasses RLS)
      const formData = new FormData();
      formData.append("file", file);
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
      const res = await fetch(`${API_BASE}/api/v1/uploads/chat`, {
        method: "POST",
        headers: { "x-user-id": userId },
        body: formData,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      const data = await res.json() as { url: string };

      const payload = {
        name: file.name,
        size: file.size,
        url: data.url,
        type: file.type || "application/octet-stream",
      };
      const text = `[FILE] ${JSON.stringify(payload)}`;
      await sendMessage(channelId, userId, text);
    } catch (err) {
      console.error("File upload failed:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleReaction = useCallback(async (messageId: string, emoji: string) => {
    if (!userId) return;
    try {
      const payload = { message_id: messageId, emoji };
      const text = `[REACTION] ${JSON.stringify(payload)}`;
      await sendMessage(channelId, userId, text);
      setActiveReactionMsg(null);
    } catch (err) {
      console.error("Reaction failed:", err);
    }
  }, [userId, channelId, sendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

    // Extract poll votes from message history
  const pollVotes = messages
    .filter(m => m.content.startsWith("[POLL_VOTE] "))
    .map(m => {
      try { return { ...JSON.parse(m.content.slice(12)), user_id: m.user_id }; }
      catch { return null; }
    })
    .filter(Boolean);

  // Extract reactions from message history
  const reactions = messages
    .filter(m => m.content.startsWith("[REACTION] "))
    .reduce((acc: Record<string, Record<string, string[]>>, m) => {
      try { 
        const parsed = JSON.parse(m.content.slice(11)); 
        if (!acc[parsed.message_id]) acc[parsed.message_id] = {};
        if (!acc[parsed.message_id][parsed.emoji]) acc[parsed.message_id][parsed.emoji] = [];
        if (!acc[parsed.message_id][parsed.emoji].includes(m.user_id)) {
          acc[parsed.message_id][parsed.emoji].push(m.user_id);
        }
      } catch {}
      return acc;
    }, {});

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      {/* Header */}
      <div className="shrink-0 px-5 py-4 border-b border-[var(--border-subtle)] flex items-center gap-4 bg-black/10 backdrop-blur-md z-10 relative shadow-sm">
        <div className="avatar avatar-sm shadow-md">
          {participantAvatar ? (
            <img src={participantAvatar} alt="" />
          ) : (
            participantName.charAt(0).toUpperCase()
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-base font-bold text-[var(--text-primary)] truncate tracking-tight">
            {participantName}
          </p>
          <p className="text-[11px] font-medium text-[var(--text-muted)] mt-0.5">
            {isConnected ? (
              <span className="text-emerald-400 drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]">● Online</span>
            ) : (
              <span>● Connecting...</span>
            )}
            {" · "}{messages.length} messages
          </p>
        </div>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={handleSynthesize}
          className={`p-2.5 rounded-xl border transition-all shadow-sm ${synthResult ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400" : "bg-white/5 border-[var(--border-subtle)] text-[var(--text-muted)] hover:text-cyan-400 hover:border-cyan-500/30 hover:bg-cyan-500/5"}`}
          title="AI Synthesize Thread"
        >
          <Sparkles className="w-4 h-4" />
        </motion.button>
      </div>

      {/* Synthesis Result */}
      <AnimatePresence>
        {synthResult && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-b border-[var(--border-subtle)] bg-cyan-500/[0.03]"
          >
            <div className="p-4 border-l-2 border-cyan-500/50 shadow-inner">
              <div className="flex items-center gap-2.5 mb-2">
                <Sparkles className="w-4 h-4 text-cyan-400" />
                <span className="text-sm font-bold text-cyan-400 tracking-tight">AI Thread Synthesis</span>
                <button onClick={() => setSynthResult(null)} className="ml-auto p-1.5 rounded-lg hover:bg-white/10 transition-colors">
                  <X className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                </button>
              </div>
              <p className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed">{synthResult}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Messages Timeline */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-6 space-y-5 scroll-smooth">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mb-4 border border-[var(--border-subtle)] shadow-lg shadow-violet-500/5">
              <MessageSquare className="w-8 h-8 text-[var(--text-muted)]" />
            </div>
            <p className="text-base font-semibold text-[var(--text-primary)] mb-1.5 tracking-tight">No messages yet</p>
            <p className="text-sm text-[var(--text-muted)] max-w-xs leading-relaxed">
              Start the conversation, share an idea, or create a poll to get started.
            </p>
          </div>
        )}

        <AnimatePresence mode="popLayout">
          {messages.map((msg) => {
            const isMine = msg.user_id === userId;
            const isPoll = msg.content.startsWith("[POLL]");
            const isIdea = msg.content.startsWith("[IDEA]");
            const isFile = msg.content.startsWith("[FILE]");
            const msgReactions = reactions[msg.id] || {};

            // Skip rendering poll votes and reactions
            if (msg.content.startsWith("[POLL_VOTE] ") || msg.content.startsWith("[REACTION] ")) return null;

            let customContent = null;
            if (msg.content.startsWith("[IDEA] ")) {
              try {
                const payload = JSON.parse(msg.content.slice(7));
                customContent = (
                  <div className="w-[460px] max-w-full text-left pointer-events-auto mt-2">
                    <LiveIdeaCard
                      postId={payload.post_id}
                      validationId={payload.validation_id}
                      ideaDescription={payload.description}
                      initialPhase="streaming"
                    />
                  </div>
                );
              } catch(e) {}
            } else if (msg.content.startsWith("[POLL] ")) {
              try {
                const payload = JSON.parse(msg.content.slice(7));
                const votesForThisPoll = pollVotes.filter(v => v.message_id === msg.id);
                customContent = (
                  <div className="mt-2">
                    <GroupPollCard
                      payload={payload}
                      messageId={msg.id}
                      votes={votesForThisPoll}
                      onVote={(idx: number) => handlePollVote(msg.id, idx)}
                      currentUserId={userId}
                    />
                  </div>
                );
              } catch(e) {}
            } else if (msg.content.startsWith("[FILE] ")) {
              try {
                const payload = JSON.parse(msg.content.slice(7));
                const isPdf = payload.type === "application/pdf" || payload.name?.endsWith(".pdf");
                const sizeKb = (payload.size / 1024).toFixed(1);
                const sizeMb = (payload.size / (1024 * 1024)).toFixed(1);
                const sizeLabel = payload.size > 1024 * 1024 ? `${sizeMb} MB` : `${sizeKb} KB`;
                customContent = (
                  <div className={`mt-2 flex items-center gap-4 px-5 py-4 rounded-2xl min-w-[260px] max-w-[360px] shadow-sm transition-all hover:-translate-y-0.5 ${
                    isMine
                      ? "bg-violet-600/20 border border-violet-500/30"
                      : "glass-card"
                  }`}>
                    {/* File icon */}
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 text-lg font-bold shadow-inner ${
                      isPdf ? "bg-rose-500/10 text-rose-400 border border-rose-500/20" : "bg-amber-400/10 text-amber-400 border border-amber-400/20"
                    }`}>
                      {isPdf ? "PDF" : <FileIcon className="w-6 h-6" />}
                    </div>
                    {/* Name & size */}
                    <div className="flex-1 min-w-0">
                      <p className="text-[15px] font-semibold text-[var(--text-primary)] truncate tracking-tight mb-0.5" title={payload.name}>
                        {payload.name}
                      </p>
                      <p className="text-xs font-medium text-[var(--text-muted)]">{sizeLabel}</p>
                    </div>
                    {/* Download */}
                    <a
                      href={payload.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      download={payload.name}
                      className="w-10 h-10 flex items-center justify-center rounded-xl bg-white/5 border border-[var(--border-subtle)] hover:bg-white/10 hover:border-white/20 transition-all shrink-0 shadow-sm"
                      title="Download"
                    >
                      <Download className="w-5 h-5 text-[var(--text-secondary)]" />
                    </a>
                  </div>
                );
              } catch(e) {}
            }

            return (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${isMine ? "justify-end" : "justify-start"} group`}
              >
                <div className="flex items-end gap-3 max-w-[85%] md:max-w-[75%]">
                  {!isMine && (
                    <div className="avatar avatar-sm shrink-0 mb-1 shadow-sm">
                      {participantAvatar ? (
                        <img src={participantAvatar} alt="" />
                      ) : (
                        participantName.charAt(0).toUpperCase()
                      )}
                    </div>
                  )}
                  <div className="relative flex flex-col">
                    {customContent ? customContent : (
                    <div
                      className={`chat-bubble text-[15px] ${
                        isMine ? "chat-bubble-sent shadow-md shadow-violet-500/10" : "chat-bubble-received shadow-sm"
                      } ${isPoll ? "border-l-2 border-l-violet-500/50" : ""} ${isIdea ? "border-l-2 border-l-cyan-500/50" : ""} ${isFile ? "border-l-2 border-l-amber-400/50" : ""}`}
                    >
                      {msg.content.split("\n").map((line, i) => (
                        <span key={i}>
                          {line.startsWith("**") && line.endsWith("**") ? (
                            <strong className="text-[var(--text-primary)] font-bold">{line.replace(/\*\*/g, "")}</strong>
                          ) : line.startsWith("_") && line.endsWith("_") ? (
                            <em className="text-[var(--text-muted)] text-[13px] font-medium">{line.replace(/_/g, "")}</em>
                          ) : (
                            line
                          )}
                          {i < msg.content.split("\n").length - 1 && <br />}
                        </span>
                      ))}
                    </div>
                    )}

                    {/* Reactions Display */}
                    {Object.keys(msgReactions).length > 0 && (
                      <div className={`flex flex-wrap gap-1.5 mt-2 ${isMine ? "justify-end" : "justify-start"} px-1`}>
                        {Object.entries(msgReactions).map(([emoji, users]) => (
                          <button
                            key={emoji}
                            onClick={() => handleReaction(msg.id, emoji)}
                            className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border transition-colors shadow-sm ${
                              users.includes(userId || "")
                                ? "bg-violet-500/15 border-violet-500/30 text-violet-300"
                                : "bg-[var(--bg-glass)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-white/10"
                            }`}
                          >
                            <span>{emoji}</span>
                            <span>{users.length}</span>
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Reply + Timestamp + Reaction Button */}
                    <div className={`flex items-center gap-3 mt-1.5 ${isMine ? "justify-end" : "justify-start"} px-2 relative`}>
                      <p className="text-[11px] font-medium text-[var(--text-muted)]">
                        {new Date(msg.created_at).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </p>
                      <button
                        onClick={() => {
                          let previewText = msg.content;
                          if (isFile) { try { previewText = `📎 ${JSON.parse(msg.content.slice(7)).name}`; } catch {} }
                          else if (isIdea) { try { previewText = `💡 ${JSON.parse(msg.content.slice(7)).description?.slice(0, 60)}...`; } catch { previewText = "💡 Idea"; } }
                          else if (isPoll) { try { previewText = `📊 ${JSON.parse(msg.content.slice(7)).question}`; } catch { previewText = "📊 Poll"; } }
                          setReplyTo({ id: msg.id, content: previewText });
                        }}
                        className="text-[11px] font-semibold text-[var(--text-muted)] hover:text-[var(--accent-violet)] opacity-0 group-hover:opacity-100 transition-all"
                      >
                        Reply
                      </button>
                      <button
                        onClick={() => setActiveReactionMsg(activeReactionMsg === msg.id ? null : msg.id)}
                        className="text-[11px] text-[var(--text-muted)] hover:text-amber-400 opacity-0 group-hover:opacity-100 transition-all"
                      >
                        <Smile className="w-3.5 h-3.5" />
                      </button>
                      
                      {/* Emoji Picker Popup */}
                      {activeReactionMsg === msg.id && (
                        <motion.div 
                          initial={{ opacity: 0, scale: 0.9 }} 
                          animate={{ opacity: 1, scale: 1 }}
                          className={`absolute top-full mt-2 z-50 flex items-center gap-1.5 p-1.5 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-full shadow-xl ${isMine ? "right-0" : "left-0"}`}
                        >
                          {["👍", "❤️", "😂", "🔥", "🚀", "👀"].map(emoji => (
                            <button
                              key={emoji}
                              onClick={() => handleReaction(msg.id, emoji)}
                              className="w-8 h-8 flex items-center justify-center text-lg hover:bg-white/10 rounded-full transition-colors"
                            >
                              {emoji}
                            </button>
                          ))}
                        </motion.div>
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Composer */}
      <div className="shrink-0 px-5 py-4 border-t border-[var(--border-subtle)] bg-black/10 backdrop-blur-lg">
        {/* Reply Preview */}
        <AnimatePresence>
          {replyTo && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden mb-3"
            >
              <div className="flex items-center gap-3 p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20 shadow-inner">
                <div className="w-1 h-full min-h-[30px] bg-violet-500/50 rounded-full" />
                <p className="text-sm font-medium text-[var(--text-secondary)] flex-1 truncate">
                  <span className="text-[var(--accent-violet)] font-bold mr-2">Replying to:</span>
                  {replyTo.content}
                </p>
                <button onClick={() => setReplyTo(null)} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
                  <X className="w-4 h-4 text-[var(--text-muted)]" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Share Idea Panel */}
        <AnimatePresence>
          {showIdeaInput && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden mb-4"
            >
              <div className="glass-card p-5 space-y-4 shadow-lg border-cyan-500/30 bg-cyan-500/[0.02]">
                <div className="flex items-center gap-2.5">
                  <Zap className="w-5 h-5 text-cyan-400" />
                  <span className="text-sm font-bold text-cyan-400 tracking-tight">Share Idea + AI Validation</span>
                  <button onClick={() => { setShowIdeaInput(false); setIdeaText(""); setIdeaMarket(""); setIdeaBudget(""); }} className="ml-auto p-1.5 rounded-lg hover:bg-white/10 transition-colors"><X className="w-4 h-4 text-[var(--text-muted)]" /></button>
                </div>
                <textarea value={ideaText} onChange={(e) => setIdeaText(e.target.value)} placeholder="Describe your startup idea in detail — what problem it solves, who it's for..." className="input-dark text-sm w-full min-h-[100px] resize-y" autoFocus />
                <div className="grid grid-cols-2 gap-3">
                  <input type="text" value={ideaMarket} onChange={(e) => setIdeaMarket(e.target.value)} placeholder="Target Market (e.g. B2B SaaS)" className="input-dark text-sm" />
                  <input type="text" value={ideaBudget} onChange={(e) => setIdeaBudget(e.target.value)} placeholder="Budget (e.g. $10k)" className="input-dark text-sm" />
                </div>
                <motion.button whileTap={{ scale: 0.98 }} onClick={handleShareIdea} disabled={!ideaText.trim() || submitting} className="btn-primary py-2.5 w-full flex items-center justify-center gap-2 disabled:opacity-50 font-semibold shadow-md">
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  {submitting ? "Submitting..." : "Share & Run AI"}
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Poll Creator */}
        <AnimatePresence>
          {showPollCreator && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden mb-4"
            >
              <div className="glass-card p-5 space-y-4 shadow-lg border-violet-500/30 bg-violet-500/[0.02]">
                <div className="flex items-center gap-2.5">
                  <BarChart3 className="w-5 h-5 text-violet-400" />
                  <span className="text-sm font-bold text-violet-400 tracking-tight">Create Poll</span>
                  <button onClick={() => { setShowPollCreator(false); setPollQuestion(""); setPollOptions(["", ""]); }} className="ml-auto p-1.5 rounded-lg hover:bg-white/10 transition-colors"><X className="w-4 h-4 text-[var(--text-muted)]" /></button>
                </div>
                <input type="text" value={pollQuestion} onChange={(e) => setPollQuestion(e.target.value)} placeholder="Poll question..." className="input-dark text-sm font-semibold" autoFocus />
                <div className="space-y-2.5">
                  {pollOptions.map((opt, i) => (
                    <input key={i} type="text" value={opt} onChange={(e) => { const n = [...pollOptions]; n[i] = e.target.value; setPollOptions(n); }} placeholder={`Option ${String.fromCharCode(65 + i)}`} className="input-dark text-sm" />
                  ))}
                </div>
                <button onClick={() => setPollOptions([...pollOptions, ""])} className="text-sm font-medium text-[var(--accent-violet)] hover:underline flex items-center gap-1">+ Add option</button>
                <motion.button whileTap={{ scale: 0.98 }} onClick={handleCreatePoll} disabled={!pollQuestion.trim() || pollOptions.filter(o => o.trim()).length < 2 || submitting} className="btn-primary py-2.5 w-full flex items-center justify-center gap-2 disabled:opacity-50 font-semibold shadow-md">
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
                  {submitting ? "Creating..." : "Send Poll"}
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Action Menu */}
        <AnimatePresence>
          {actionMenuOpen && !showIdeaInput && !showPollCreator && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="action-menu mb-3">
              <button onClick={() => { setShowIdeaInput(true); setActionMenuOpen(false); }} className="action-menu-item w-full py-3">
                <Zap className="w-4 h-4 text-cyan-400" /><span className="font-medium">Share Idea (Run AI)</span>
              </button>
              <button onClick={() => { setShowPollCreator(true); setActionMenuOpen(false); }} className="action-menu-item w-full py-3">
                <BarChart3 className="w-4 h-4 text-violet-400" /><span className="font-medium">Create Poll</span>
              </button>
              <button onClick={() => {
                const input = document.createElement("input");
                input.type = "file";
                input.accept = "*/*";
                input.onchange = async (e) => {
                  const file = (e.target as HTMLInputElement).files?.[0];
                  if (file) {
                    await handleFileUpload(file);
                  }
                };
                input.click();
              }} className="action-menu-item w-full py-3">
                <FileUp className="w-4 h-4 text-amber-400" /><span className="font-medium">Upload File</span>
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex items-center gap-3">
          <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }} onClick={() => setActionMenuOpen(p => !p)}
            className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all shrink-0 ${actionMenuOpen ? "bg-[var(--accent-violet)] text-white shadow-md shadow-violet-500/20" : "bg-white/5 border border-[var(--border-subtle)] text-[var(--text-muted)] hover:bg-white/10 hover:text-[var(--text-primary)]"}`}>
            {actionMenuOpen ? <X className="w-5 h-5" /> : <Plus className="w-5 h-5" />}
          </motion.button>
          <div className="flex-1 relative">
            <input type="text" value={inputText} onChange={(e) => setInputText(e.target.value)} onKeyDown={handleKeyDown} placeholder="Type a message..." className="input-dark w-full py-3 pl-4 pr-12 text-sm shadow-inner rounded-xl" />
            <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }} onClick={handleSend} disabled={!inputText.trim()}
              className={`absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 rounded-lg flex items-center justify-center transition-all ${inputText.trim() ? "bg-[var(--accent-violet)] text-white shadow-md shadow-violet-500/30" : "text-[var(--text-muted)] hover:bg-white/5"}`}>
              <Send className="w-4 h-4 ml-0.5" />
            </motion.button>
          </div>
        </div>
      </div>
    </div>
  );
}
