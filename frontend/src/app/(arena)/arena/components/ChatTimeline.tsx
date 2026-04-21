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
      const res = await fetch(`http://127.0.0.1:8000/api/v1/uploads/chat`, {
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
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-[var(--border-subtle)] flex items-center gap-3">
        <div className="avatar avatar-sm">
          {participantAvatar ? (
            <img src={participantAvatar} alt="" />
          ) : (
            participantName.charAt(0).toUpperCase()
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-[var(--text-primary)] truncate">
            {participantName}
          </p>
          <p className="text-[10px] text-[var(--text-muted)]">
            {isConnected ? (
              <span className="text-emerald-400">● Online</span>
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
          className={`btn-icon text-xs ${synthResult ? "text-cyan-400" : ""}`}
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
            className="overflow-hidden border-b border-[var(--border-subtle)]"
          >
            <div className="p-3 bg-cyan-500/5 border-l-2 border-cyan-500/40">
              <div className="flex items-center gap-2 mb-1">
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-xs font-semibold text-cyan-400">AI Thread Synthesis</span>
                <button onClick={() => setSynthResult(null)} className="ml-auto btn-icon">
                  <X className="w-3 h-3" />
                </button>
              </div>
              <p className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap">{synthResult}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Messages Timeline */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500/10 to-cyan-500/10 flex items-center justify-center mb-3 border border-[var(--border-subtle)]">
              <MessageSquare className="w-6 h-6 text-[var(--text-muted)]" />
            </div>
            <p className="text-sm text-[var(--text-secondary)] mb-1">No messages yet</p>
            <p className="text-xs text-[var(--text-muted)]">
              Start the conversation, share an idea, or create a poll
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
                  <div className="w-[460px] max-w-full text-left pointer-events-auto mt-1">
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
                  <div className="mt-1">
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
                  <div className={`mt-1 flex items-center gap-3 px-4 py-3 rounded-2xl min-w-[240px] max-w-[340px] border ${
                    isMine
                      ? "bg-violet-600/30 border-violet-500/40"
                      : "bg-[var(--bg-secondary)] border-[var(--border-subtle)]"
                  }`}>
                    {/* File icon */}
                    <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 text-lg font-bold ${
                      isPdf ? "bg-red-500/20 text-red-400" : "bg-amber-400/15 text-amber-400"
                    }`}>
                      {isPdf ? "PDF" : <FileIcon className="w-5 h-5" />}
                    </div>
                    {/* Name & size */}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-[var(--text-primary)] truncate leading-tight" title={payload.name}>
                        {payload.name}
                      </p>
                      <p className="text-xs text-[var(--text-muted)] mt-0.5">{sizeLabel}</p>
                    </div>
                    {/* Download */}
                    <a
                      href={payload.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      download={payload.name}
                      className="w-8 h-8 flex items-center justify-center rounded-full bg-white/10 hover:bg-white/20 transition-colors shrink-0"
                      title="Download"
                    >
                      <Download className="w-4 h-4 text-[var(--text-secondary)]" />
                    </a>
                  </div>
                );
              } catch(e) {}
            }

            return (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${isMine ? "justify-end" : "justify-start"} group`}
              >
                <div className="flex items-end gap-2 max-w-[92%]">
                  {!isMine && (
                    <div className="avatar avatar-sm shrink-0 mb-0.5">
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
                      className={`chat-bubble ${
                        isMine ? "chat-bubble-sent" : "chat-bubble-received"
                      } ${isPoll ? "border-l-2 border-violet-500/40" : ""} ${isIdea ? "border-l-2 border-cyan-500/40" : ""} ${isFile ? "border-l-2 border-amber-400/40" : ""}`}
                    >
                      {msg.content.split("\n").map((line, i) => (
                        <span key={i}>
                          {line.startsWith("**") && line.endsWith("**") ? (
                            <strong className="text-[var(--text-primary)]">{line.replace(/\*\*/g, "")}</strong>
                          ) : line.startsWith("_") && line.endsWith("_") ? (
                            <em className="text-[var(--text-muted)] text-xs">{line.replace(/_/g, "")}</em>
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
                      <div className={`flex flex-wrap gap-1 mt-1 ${isMine ? "justify-end" : "justify-start"} px-1`}>
                        {Object.entries(msgReactions).map(([emoji, users]) => (
                          <button
                            key={emoji}
                            onClick={() => handleReaction(msg.id, emoji)}
                            className={`flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] border transition-colors ${
                              users.includes(userId || "")
                                ? "bg-violet-500/20 border-violet-500/40 text-violet-300"
                                : "bg-[var(--bg-glass)] border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-white/5"
                            }`}
                          >
                            <span>{emoji}</span>
                            <span>{users.length}</span>
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Reply + Timestamp + Reaction Button */}
                    <div className={`flex items-center gap-2 mt-0.5 ${isMine ? "justify-end" : "justify-start"} px-1 relative`}>
                      <p className="text-[10px] text-[var(--text-muted)]">
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
                        className="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent-violet)] opacity-0 group-hover:opacity-100 transition-all"
                      >
                        Reply
                      </button>
                      <button
                        onClick={() => setActiveReactionMsg(activeReactionMsg === msg.id ? null : msg.id)}
                        className="text-[10px] text-[var(--text-muted)] hover:text-amber-400 opacity-0 group-hover:opacity-100 transition-all"
                      >
                        <Smile className="w-3 h-3" />
                      </button>
                      
                      {/* Emoji Picker Popup */}
                      {activeReactionMsg === msg.id && (
                        <div className={`absolute top-full mt-1 z-50 flex items-center gap-1 p-1 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-full shadow-lg ${isMine ? "right-0" : "left-0"}`}>
                          {["👍", "❤️", "😂", "🔥", "🚀", "👀"].map(emoji => (
                            <button
                              key={emoji}
                              onClick={() => handleReaction(msg.id, emoji)}
                              className="w-6 h-6 flex items-center justify-center text-sm hover:bg-white/10 rounded-full transition-colors"
                            >
                              {emoji}
                            </button>
                          ))}
                        </div>
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
      <div className="shrink-0 px-4 py-3 border-t border-[var(--border-subtle)]">
        {/* Reply Preview */}
        <AnimatePresence>
          {replyTo && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden mb-2"
            >
              <div className="flex items-center gap-2 p-2 rounded-lg bg-violet-500/5 border border-violet-500/10">
                <div className="w-0.5 h-full min-h-[24px] bg-violet-500/40 rounded-full" />
                <p className="text-xs text-[var(--accent-violet)] flex-1 truncate">{replyTo.content}</p>
                <button onClick={() => setReplyTo(null)} className="btn-icon">
                  <X className="w-3 h-3" />
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
              className="overflow-hidden mb-3"
            >
              <div className="glass-card p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <Zap className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs font-semibold text-cyan-400">Share Idea + AI Validation</span>
                  <button onClick={() => { setShowIdeaInput(false); setIdeaText(""); setIdeaMarket(""); setIdeaBudget(""); }} className="ml-auto btn-icon"><X className="w-3 h-3" /></button>
                </div>
                <textarea value={ideaText} onChange={(e) => setIdeaText(e.target.value)} placeholder="Describe your startup idea in detail — what problem it solves, who it's for..." className="input-dark text-sm w-full" rows={3} autoFocus />
                <div className="grid grid-cols-2 gap-2">
                  <input type="text" value={ideaMarket} onChange={(e) => setIdeaMarket(e.target.value)} placeholder="Target Market (e.g. B2B SaaS)" className="input-dark text-xs" />
                  <input type="text" value={ideaBudget} onChange={(e) => setIdeaBudget(e.target.value)} placeholder="Budget (e.g. $10k)" className="input-dark text-xs" />
                </div>
                <motion.button whileTap={{ scale: 0.98 }} onClick={handleShareIdea} disabled={!ideaText.trim() || submitting} className="btn-primary text-xs w-full flex items-center justify-center gap-1.5 disabled:opacity-50">
                  {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Zap className="w-3.5 h-3.5" />}
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
              className="overflow-hidden mb-3"
            >
              <div className="glass-card p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-violet-400" />
                  <span className="text-xs font-semibold text-violet-400">Create Poll</span>
                  <button onClick={() => { setShowPollCreator(false); setPollQuestion(""); setPollOptions(["", ""]); }} className="ml-auto btn-icon"><X className="w-3 h-3" /></button>
                </div>
                <input type="text" value={pollQuestion} onChange={(e) => setPollQuestion(e.target.value)} placeholder="Poll question..." className="input-dark text-sm" autoFocus />
                {pollOptions.map((opt, i) => (
                  <input key={i} type="text" value={opt} onChange={(e) => { const n = [...pollOptions]; n[i] = e.target.value; setPollOptions(n); }} placeholder={`Option ${String.fromCharCode(65 + i)}`} className="input-dark text-xs" />
                ))}
                <button onClick={() => setPollOptions([...pollOptions, ""])} className="text-xs text-[var(--accent-violet)] hover:underline">+ Add option</button>
                <motion.button whileTap={{ scale: 0.98 }} onClick={handleCreatePoll} disabled={!pollQuestion.trim() || pollOptions.filter(o => o.trim()).length < 2 || submitting} className="btn-primary text-xs w-full flex items-center justify-center gap-1.5 disabled:opacity-50">
                  {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <BarChart3 className="w-3.5 h-3.5" />}
                  {submitting ? "Creating..." : "Send Poll"}
                </motion.button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Action Menu */}
        <AnimatePresence>
          {actionMenuOpen && !showIdeaInput && !showPollCreator && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="action-menu mb-2">
              <button onClick={() => { setShowIdeaInput(true); setActionMenuOpen(false); }} className="action-menu-item w-full">
                <Zap className="w-4 h-4 text-cyan-400" /><span>Share Idea (Run AI)</span>
              </button>
              <button onClick={() => { setShowPollCreator(true); setActionMenuOpen(false); }} className="action-menu-item w-full">
                <BarChart3 className="w-4 h-4 text-violet-400" /><span>Create Poll</span>
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
              }} className="action-menu-item w-full">
                <FileUp className="w-4 h-4 text-amber-400" /><span>Upload File</span>
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex items-center gap-2">
          <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }} onClick={() => setActionMenuOpen(p => !p)}
            className={`btn-icon shrink-0 ${actionMenuOpen ? "bg-[var(--accent-violet)]/10 border-[var(--accent-violet)]/30 text-[var(--accent-violet)]" : ""}`}>
            {actionMenuOpen ? <X className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
          </motion.button>
          <input type="text" value={inputText} onChange={(e) => setInputText(e.target.value)} onKeyDown={handleKeyDown} placeholder="Type a message..." className="input-dark flex-1 py-2.5 text-sm" />
          <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }} onClick={handleSend} disabled={!inputText.trim()}
            className={`btn-icon shrink-0 ${inputText.trim() ? "bg-[var(--accent-violet)] border-[var(--accent-violet)] text-white" : ""}`}>
            <Send className="w-4 h-4" />
          </motion.button>
        </div>
      </div>
    </div>
  );
}
