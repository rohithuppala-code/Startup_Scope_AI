"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import {
  ArrowBigUp,
  ArrowBigDown,
  MessageSquare,
  Sparkles,
  Tag,
  ChevronDown,
  ChevronUp,
  DollarSign,
  Users2,
  BarChart3,
  Zap,
  Clock,
  ExternalLink,
  Send,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";
import { useWebSocket } from "@/hooks/use-websocket";
import StreamingProgress from "./StreamingProgress";

type CardPhase = "submitting" | "streaming" | "completed" | "interactive";

interface LiveIdeaCardProps {
  // For completed posts loaded from feed
  postId?: string;
  title?: string;
  content?: string;
  authorId?: string;
  authorUsername?: string;
  authorAvatar?: string | null;
  upvoteCount?: number;
  downvoteCount?: number;
  commentCount?: number;
  tags?: string[];
  createdAt?: string;
  reportJson?: Record<string, unknown> | null;
  validationId?: string | null;
  karmaScore?: number;
  pollData?: {
    id: string;
    question: string;
    options: { id: string; text: string; votes?: number }[];
    expires_at?: string | null;
  } | null;
  // For live streaming cards (initiated by composer)
  initialPhase?: CardPhase;
  ideaDescription?: string;
  onPhaseChange?: (phase: CardPhase) => void;
}

export default function LiveIdeaCard({
  postId,
  title,
  content,
  authorId,
  authorUsername = "unknown",
  authorAvatar,
  upvoteCount = 0,
  downvoteCount = 0,
  commentCount = 0,
  tags = [],
  createdAt,
  reportJson,
  validationId: initialValidationId,
  karmaScore: initialKarma,
  pollData,
  initialPhase = "interactive",
  ideaDescription,
  onPhaseChange,
}: LiveIdeaCardProps) {
  const userId = useUserStore((s) => s.userId);
  const [phase, setPhase] = useState<CardPhase>(initialPhase);
  const [validationId, setValidationId] = useState(initialValidationId ?? null);
  const [report, setReport] = useState<Record<string, unknown> | null>(reportJson ?? null);
  const [score, setScore] = useState(initialKarma ?? upvoteCount - downvoteCount);
  const [votes, setVotes] = useState({ up: upvoteCount, down: downvoteCount });
  const [expandedTab, setExpandedTab] = useState<string | null>(null);
  const [synthesis, setSynthesis] = useState<string | null>(null);
  const [synthesizing, setSynthesizing] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [showComments, setShowComments] = useState(false);
  const [comments, setComments] = useState<{id: string; author_username: string; content: string; created_at: string | null}[]>([]);
  const [commentText, setCommentText] = useState("");
  const [commentLoading, setCommentLoading] = useState(false);
  const [localCommentCount, setLocalCommentCount] = useState(commentCount);
  const { sections, status: wsStatus, connect } = useWebSocket();

  // Mutable local title/content that can be populated from the AI report
  const [liveTitle, setLiveTitle] = useState(title || (ideaDescription ? ideaDescription.slice(0, 60) + (ideaDescription.length > 60 ? "..." : "") : ""));
  const [liveContent, setLiveContent] = useState(content || ideaDescription || "");

  // Determine effective phase from WS status
  useEffect(() => {
    if (phase === "streaming") {
      if (wsStatus === "completed") {
        setPhase("completed");
        onPhaseChange?.("completed");
        // Extract report from WS sections
        const reportSection = sections.find((s) => s.section === "report" || s.section === "consensus");
        if (reportSection) {
          setReport(reportSection.data);
          // Populate title from report if not already set
          const r = reportSection.data;
          if (!title && r) {
            const reportTitle = (r as Record<string,unknown>).idea_title || (r as Record<string,unknown>).title;
            if (typeof reportTitle === "string") setLiveTitle(reportTitle);
          }
        }
      } else if (wsStatus === "failed") {
        setPhase("completed");
        onPhaseChange?.("completed");
      }
    }
  }, [wsStatus, phase, sections, onPhaseChange, title]);

  // Connect WS when streaming starts
  useEffect(() => {
    if (phase === "streaming" && validationId) {
      connect(validationId);
    }
  }, [phase, validationId, connect]);

  const feasibilityScore = useMemo(() => {
    if (!report) return null;
    const r = report as Record<string, unknown>;
    const consensus = r.consensus_confidence ?? r.feasibility_score ?? r.score;
    if (typeof consensus === "number") {
      return consensus <= 1.0 ? Math.round(consensus * 100) : Math.round(consensus);
    }
    return null;
  }, [report]);

  const scoreClass = useMemo(() => {
    if (feasibilityScore === null) return "";
    if (feasibilityScore >= 70) return "score-badge-high";
    if (feasibilityScore >= 40) return "score-badge-medium";
    return "score-badge-low";
  }, [feasibilityScore]);

  const handleVote = useCallback(
    async (direction: 1 | -1) => {
      if (!userId || !postId) return;
      try {
        const res = await api<{ new_score: number }>(
          `/api/v1/arena/posts/${postId}/vote`,
          { method: "POST", userId, body: { direction } }
        );
        setScore(res.new_score);
        setVotes((prev) => ({
          up: direction === 1 ? prev.up + 1 : prev.up,
          down: direction === -1 ? prev.down + 1 : prev.down,
        }));
      } catch (err) {
        console.error("[LiveIdeaCard] Vote error:", err);
      }
    },
    [userId, postId]
  );

  const completedSections = sections.map((s) => s.section.replace("_", "").toLowerCase());

  // ─── SUBMITTING Phase ───
  if (phase === "submitting") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-6 streaming-glow"
      >
        <div className="flex items-center gap-3 mb-4">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
            className="w-10 h-10 rounded-xl bg-cyan-500/10 flex items-center justify-center shrink-0 shadow-lg shadow-cyan-500/20"
          >
            <Zap className="w-5 h-5 text-cyan-400" />
          </motion.div>
          <div>
            <p className="text-base font-bold text-[var(--text-primary)] tracking-tight">Submitting idea...</p>
            <p className="text-sm text-[var(--text-muted)]">Queueing for AI validation</p>
          </div>
        </div>
        <div className="glass-card p-4 bg-cyan-500/[0.03] border-cyan-500/20">
          <p className="text-sm text-[var(--text-secondary)] line-clamp-2 leading-relaxed">
            {ideaDescription || content || "Processing..."}
          </p>
        </div>
      </motion.div>
    );
  }

  // ─── STREAMING Phase ───
  if (phase === "streaming") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card p-6 streaming-glow border-cyan-500/30"
      >
        <div className="flex items-center gap-4 mb-5">
          <div className="avatar avatar-lg shrink-0 shadow-lg shadow-violet-500/20">
            {authorAvatar ? (
              <img src={authorAvatar} alt="" />
            ) : (
              authorUsername.charAt(0).toUpperCase()
            )}
          </div>
          <div className="min-w-0">
            <p className="text-base font-bold text-[var(--text-primary)] truncate tracking-tight">
              {title || "AI Validation in Progress"}
            </p>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              by <span className="text-[var(--accent-violet)] font-semibold">@{authorUsername}</span>
            </p>
          </div>
          <div className="ml-auto shrink-0">
            <span className="text-[10px] px-3 py-1.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 streaming-pulse font-bold tracking-widest shadow-[0_0_12px_rgba(6,182,212,0.2)]">
              <Clock className="w-3.5 h-3.5 inline mr-1.5" />
              LIVE
            </span>
          </div>
        </div>

        {/* Idea description */}
        <div className="glass-card p-4 mb-5 bg-white/[0.02]">
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
            {ideaDescription || content || "Running AI analysis..."}
          </p>
        </div>

        {/* AI Pipeline Progress */}
        <StreamingProgress completedSections={completedSections} status={wsStatus === "idle" ? "connecting" : wsStatus} />
      </motion.div>
    );
  }

  // ─── COMPLETED / INTERACTIVE Phase ───
  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card glass-card-hover p-6"
    >
      <div className="flex gap-5">
        {/* Vote Column */}
        <div className="flex flex-col items-center gap-1 shrink-0">
          <motion.button
            whileHover={{ scale: 1.15, y: -2 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => handleVote(1)}
            className="p-2 rounded-xl hover:bg-emerald-500/15 transition-all duration-300 group shadow-sm hover:shadow-emerald-500/20"
          >
            <ArrowBigUp className="w-6 h-6 text-[var(--text-muted)] group-hover:text-emerald-400 transition-colors drop-shadow-sm" />
          </motion.button>
          <span
            className={`text-base font-extrabold tabular-nums transition-colors duration-300 ${
              score > 0
                ? "text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]"
                : score < 0
                ? "text-rose-400"
                : "text-[var(--text-muted)]"
            }`}
          >
            {score}
          </span>
          <motion.button
            whileHover={{ scale: 1.15, y: 2 }}
            whileTap={{ scale: 0.9 }}
            onClick={() => handleVote(-1)}
            className="p-2 rounded-xl hover:bg-rose-500/15 transition-all duration-300 group shadow-sm hover:shadow-rose-500/20"
          >
            <ArrowBigDown className="w-6 h-6 text-[var(--text-muted)] group-hover:text-rose-400 transition-colors drop-shadow-sm" />
          </motion.button>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex items-center gap-3 min-w-0">
              <div className="avatar avatar-sm shrink-0 shadow-md">
                {authorAvatar ? (
                  <img src={authorAvatar} alt="" />
                ) : (
                  authorUsername.charAt(0).toUpperCase()
                )}
              </div>
              <div className="min-w-0">
                <h3 className="font-bold text-lg text-[var(--text-primary)] truncate tracking-tight">
                  {liveTitle || liveContent?.slice(0, 60)}
                </h3>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  by{" "}
                  <span className="text-[var(--accent-violet)] font-semibold hover:underline cursor-pointer transition-all">
                    @{authorUsername}
                  </span>{" "}
                  · {createdAt ? new Date(createdAt).toLocaleDateString() : "just now"}
                </p>
              </div>
            </div>

            {/* Feasibility Score Badge */}
            {feasibilityScore !== null && (
              <div className={`score-badge ${scoreClass} shrink-0 px-3 py-1.5 shadow-sm`}>
                <Zap className="w-3.5 h-3.5" />
                {feasibilityScore}%
              </div>
            )}
          </div>

          {/* Content Preview */}
          {liveContent && (
            <p className="text-[15px] text-[var(--text-secondary)] mt-3 line-clamp-3 leading-relaxed">
              {liveContent}
            </p>
          )}

          {/* Tags */}
          {(tags || []).length > 0 && (
            <div className="flex flex-wrap gap-2 mt-4">
              {(tags || []).slice(0, 3).map((tag, i) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1.5 text-[11px] px-3 py-1 rounded-full bg-violet-500/10 text-violet-300 border border-violet-500/20 shadow-sm"
                >
                  <Tag className="w-3 h-3" />
                  {tag}
                </span>
              ))}
            </div>
          )}

          {/* Expandable Report Tabs */}
          {report && (
            <div className="mt-4 space-y-2">
              <div className="tab-bar p-1 bg-black/20">
                {["competitors", "pricing", "market"].map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setExpandedTab(expandedTab === tab ? null : tab)}
                    className={`tab-item py-1.5 px-4 ${expandedTab === tab ? "tab-item-active" : ""}`}
                  >
                    {tab === "competitors" && <Users2 className="w-3.5 h-3.5 inline mr-1.5" />}
                    {tab === "pricing" && <DollarSign className="w-3.5 h-3.5 inline mr-1.5" />}
                    {tab === "market" && <BarChart3 className="w-3.5 h-3.5 inline mr-1.5" />}
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>

              <AnimatePresence mode="wait">
                {expandedTab && (
                  <motion.div
                    key={expandedTab}
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
                    className="overflow-hidden"
                  >
                    <div className="glass-card p-4 text-sm text-[var(--text-secondary)] whitespace-pre-wrap max-h-60 overflow-y-auto leading-relaxed border-t-0 rounded-t-none bg-black/10">
                      {(() => {
                        const r = report as Record<string, unknown>;
                        const data = r[expandedTab] ?? r[`${expandedTab}_data`] ?? r[`${expandedTab}_analysis`];
                        if (data && typeof data === "object") {
                          return JSON.stringify(data, null, 2);
                        }
                        return `No ${expandedTab} data available in this report.`;
                      })()}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Footer Actions */}
          <div className="flex items-center gap-5 mt-5 pt-4 border-t border-[var(--border-subtle)]">
            <button
              onClick={async () => {
                setShowComments(!showComments);
                if (!showComments && postId && comments.length === 0) {
                  try {
                    const res = await api<{id: string; author_username: string; content: string; created_at: string | null}[]>(
                      `/api/v1/arena/posts/${postId}/comments`
                    );
                    setComments(res);
                  } catch { /* ok */ }
                }
              }}
              className={`flex items-center gap-2 text-sm font-medium transition-colors ${
                showComments ? "text-[var(--accent-violet)]" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              }`}
            >
              <MessageSquare className="w-4 h-4" />
              {localCommentCount} comments
            </button>
            <button
              onClick={async () => {
                if (synthesizing) return;
                if (synthesis) { setSynthesis(null); return; }
                setSynthesizing(true);
                try {
                  // Use the AI summarize endpoint — sends report_json + markdown_report to Gemini
                  const vid = validationId;
                  if (vid) {
                    const res = await api<{ summary: string }>(`/api/v1/validate/${vid}/summarize`, {
                      method: "POST",
                    });
                    setSynthesis(res.summary || "Summary unavailable.");
                  } else if (postId) {
                    // Fallback for arena posts
                    const res = await api<{ synthesis?: string; summary?: string }>(`/api/v1/arena/posts/${postId}/synthesize`, {
                      method: "POST",
                      userId: userId || "",
                    });
                    setSynthesis(res.synthesis || res.summary || "Summary unavailable.");
                  } else {
                    setSynthesis((ideaDescription || content) ? `**Idea:**\n${ideaDescription || content}` : "AI analysis is still processing. Please wait and try again.");
                  }
                } catch {
                  setSynthesis((ideaDescription || content) ? `**Idea:**\n${ideaDescription || content}` : "Summary unavailable.");
                } finally {
                  setSynthesizing(false);
                }
              }}
              className={`flex items-center gap-2 text-sm font-medium transition-colors ${
                synthesis ? "text-cyan-400" : "text-[var(--text-muted)] hover:text-cyan-400"
              }`}
            >
              {synthesizing ? (
                <motion.div animate={{ rotate: 360 }} transition={{ duration: 1, repeat: Infinity, ease: "linear" }}>
                  <Sparkles className="w-4 h-4" />
                </motion.div>
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              {synthesis ? "Hide" : "AI Summary"}
            </button>
            {postId && (
              <button
                onClick={() => setShowDetails(!showDetails)}
                className={`ml-auto flex items-center gap-1.5 text-sm font-medium transition-colors ${
                  showDetails ? "text-[var(--accent-violet)]" : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                <ExternalLink className="w-4 h-4" />
                {showDetails ? "Hide" : "Details"}
              </button>
            )}
          </div>

          {/* Synthesis Result */}
          <AnimatePresence>
            {synthesis && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="glass-card p-5 mt-4 border-l-2 border-cyan-500/50 bg-cyan-500/[0.03] shadow-lg shadow-cyan-500/5">
                  <div className="flex items-center gap-2.5 mb-4">
                    <Sparkles className="w-5 h-5 text-cyan-400" />
                    <span className="text-sm font-bold text-cyan-400 tracking-tight">AI Idea Summary</span>
                  </div>
                  <div className="text-sm text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed space-y-2">
                    <ReactMarkdown
                      components={{
                        h1: ({node, ...props}) => <h3 className="text-base font-bold mt-4 mb-2 text-[var(--text-primary)]" {...props}/>,
                        h2: ({node, ...props}) => <h4 className="text-[15px] font-bold mt-4 mb-2 text-[var(--text-primary)]" {...props}/>,
                        h3: ({node, ...props}) => <h5 className="text-sm font-semibold mt-3 mb-1.5 text-[var(--text-primary)]" {...props}/>,
                        p: ({node, ...props}) => <p className="text-sm text-[var(--text-secondary)] mb-3 leading-relaxed" {...props}/>,
                        ul: ({node, ...props}) => <ul className="list-disc list-inside space-y-1.5 mb-3 text-sm text-[var(--text-secondary)]" {...props}/>,
                        li: ({node, ...props}) => <li className="ml-2" {...props}/>,
                        strong: ({node, ...props}) => <strong className="font-bold text-[var(--text-primary)]" {...props}/>,
                      }}
                    >
                      {synthesis}
                    </ReactMarkdown>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Details Panel */}
          <AnimatePresence>
            {showDetails && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="glass-card p-5 mt-4 text-sm text-[var(--text-secondary)] space-y-3 bg-black/20">
                  <div className="flex justify-between items-center border-b border-[var(--border-subtle)] pb-2">
                    <span className="text-[var(--text-muted)] font-medium">Post ID</span>
                    <span className="font-mono text-xs bg-white/5 px-2 py-1 rounded">{postId?.slice(0, 12)}...</span>
                  </div>
                  {validationId && (
                    <div className="flex justify-between items-center border-b border-[var(--border-subtle)] pb-2">
                      <span className="text-[var(--text-muted)] font-medium">Validation ID</span>
                      <span className="font-mono text-xs bg-white/5 px-2 py-1 rounded">{validationId.slice(0, 12)}...</span>
                    </div>
                  )}
                  <div className="flex justify-between items-center border-b border-[var(--border-subtle)] pb-2">
                    <span className="text-[var(--text-muted)] font-medium">Votes</span>
                    <span className="font-medium text-[var(--text-primary)]">↑{votes.up} ↓{votes.down}</span>
                  </div>
                  <div className="flex justify-between items-center border-b border-[var(--border-subtle)] pb-2">
                    <span className="text-[var(--text-muted)] font-medium">Comments</span>
                    <span className="font-medium text-[var(--text-primary)]">{commentCount}</span>
                  </div>
                  {feasibilityScore !== null && (
                    <div className="flex justify-between items-center border-b border-[var(--border-subtle)] pb-2">
                      <span className="text-[var(--text-muted)] font-medium">Feasibility</span>
                      <span className={`font-bold ${feasibilityScore >= 70 ? "text-emerald-400" : feasibilityScore >= 40 ? "text-amber-400" : "text-rose-400"}`}>{feasibilityScore}%</span>
                    </div>
                  )}
                  {createdAt && (
                    <div className="flex justify-between items-center">
                      <span className="text-[var(--text-muted)] font-medium">Created</span>
                      <span className="text-[var(--text-primary)]">{new Date(createdAt).toLocaleString()}</span>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Comments Section */}
          <AnimatePresence>
            {showComments && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="mt-4 space-y-3">
                  {/* Comment Input */}
                  <div className="flex items-center gap-3">
                    <input
                      type="text"
                      value={commentText}
                      onChange={(e) => setCommentText(e.target.value)}
                      onKeyDown={async (e) => {
                        if (e.key === "Enter" && commentText.trim() && postId && userId && !commentLoading) {
                          setCommentLoading(true);
                          try {
                            const res = await api<{id: string; author_username: string; content: string; created_at: string | null}>(
                              `/api/v1/arena/posts/${postId}/comments`,
                              { method: "POST", userId, body: { content: commentText.trim() } }
                            );
                            setComments((prev) => [res, ...prev]);
                            setLocalCommentCount((c) => c + 1);
                            setCommentText("");
                          } catch (err) {
                            console.error("[Comment] Error:", err);
                          } finally {
                            setCommentLoading(false);
                          }
                        }
                      }}
                      placeholder="Write a comment..."
                      className="input-dark flex-1 text-sm py-2.5 shadow-inner"
                    />
                    <button
                      onClick={async () => {
                        if (!commentText.trim() || !postId || !userId || commentLoading) return;
                        setCommentLoading(true);
                        try {
                          const res = await api<{id: string; author_username: string; content: string; created_at: string | null}>(
                            `/api/v1/arena/posts/${postId}/comments`,
                            { method: "POST", userId, body: { content: commentText.trim() } }
                          );
                          setComments((prev) => [res, ...prev]);
                          setLocalCommentCount((c) => c + 1);
                          setCommentText("");
                        } catch (err) {
                          console.error("[Comment] Error:", err);
                        } finally {
                          setCommentLoading(false);
                        }
                      }}
                      disabled={!commentText.trim() || commentLoading}
                      className="btn-primary p-2.5 shrink-0 rounded-xl disabled:opacity-50"
                    >
                      {commentLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                  </div>

                  {/* Comments List */}
                  {comments.length === 0 ? (
                    <div className="glass-card p-6 text-center">
                      <MessageSquare className="w-6 h-6 text-[var(--text-muted)] mx-auto mb-2 opacity-50" />
                      <p className="text-sm text-[var(--text-muted)]">No comments yet. Be the first to share your thoughts!</p>
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                      {comments.map((c) => (
                        <div key={c.id} className="glass-card p-3.5 bg-black/10">
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-sm font-semibold text-[var(--accent-violet)] hover:underline cursor-pointer">@{c.author_username}</span>
                            {c.created_at && (
                              <span className="text-[11px] text-[var(--text-muted)]">
                                {new Date(c.created_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{c.content}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
}
