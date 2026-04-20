"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/hooks/use-auth";
import { useWebSocket, type WSSection } from "@/hooks/use-websocket";
import { api } from "@/lib/api";
import {
  Send,
  Loader2,
  FileDown,
  GitCompare,
  Upload,
  CheckCircle2,
  XCircle,
  Sparkles,
  TrendingUp,
  Shield,
  DollarSign,
  Users,
  Lightbulb,
  X,
} from "lucide-react";

import { CompareModal } from "./CompareModal";
import { ComparisonReportModal } from "./ComparisonReportModal";

const sectionIcons: Record<string, React.ElementType> = {
  market_analysis: TrendingUp,
  competitor_analysis: Users,
  pricing: DollarSign,
  patents: Shield,
  consensus: Sparkles,
  recommendation: Lightbulb,
  funding: TrendingUp,
  sentiment: Users,
  jobs: Lightbulb,
  traffic: TrendingUp,
};

const sectionLabels: Record<string, string> = {
  market_analysis: "Market Analysis",
  competitor_analysis: "Competitor Landscape",
  pricing: "Pricing Intelligence",
  patents: "Patent Research",
  consensus: "Multi-Model Consensus",
  recommendation: "Final Recommendation",
  funding: "Funding Intelligence",
  sentiment: "Social Sentiment",
  jobs: "Job Market Signal",
  traffic: "Web Traffic Analysis",
};

export default function StudioPage() {
  const router = useRouter();
  const { userId } = useAuth();
  const { sections, status, connect } = useWebSocket();
  const [idea, setIdea] = useState("");
  const [market, setMarket] = useState("");
  const [budget, setBudget] = useState("");
  const [validationId, setValidationId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  
  const [showPublish, setShowPublish] = useState(false);
  const [publishTitle, setPublishTitle] = useState("");
  const [publishTags, setPublishTags] = useState("");
  const [publishing, setPublishing] = useState(false);

  const [showCompareSelect, setShowCompareSelect] = useState(false);
  const [comparisonReport, setComparisonReport] = useState<any>(null);
  const [comparing, setComparing] = useState(false);

  const handleSubmit = async () => {
    if (!idea.trim() || !userId) return;
    setSubmitting(true);
    try {
      const res = await api<{ validation_id: string }>("/api/v1/validate", {
        method: "POST",
        userId,
        body: {
          idea_description: idea,
          target_market: market || undefined,
          budget_constraints: budget || undefined,
        },
      });
      setValidationId(res.validation_id);
      connect(res.validation_id);
    } catch (err) {
      console.error("Submit error:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const handleExport = async () => {
    if (!validationId) return;
    try {
      const res = await api<{ download_url: string }>(
        `/api/v1/export/${validationId}/pdf`
      );
      window.open(res.download_url, "_blank");
    } catch (err) {
      console.error("Export error:", err);
    }
  };

  const handlePublish = async () => {
    if (!validationId || !userId || !publishTitle.trim()) return;
    setPublishing(true);
    try {
      await api("/api/v1/arena/publish", {
        method: "POST",
        userId,
        body: {
          validation_id: validationId,
          title: publishTitle.trim(),
          tags: publishTags
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
        },
      });
      setShowPublish(false);
      router.push("/arena");
    } catch (err) {
      console.error("Publish error:", err);
    } finally {
      setPublishing(false);
    }
  };

  const handleRunComparison = async (validationIds: string[]) => {
    if (!userId) return;
    setShowCompareSelect(false);
    setComparing(true);
    try {
      const report = await api("/api/v1/compare", {
        method: "POST",
        userId,
        body: { validation_ids: validationIds },
      });
      setComparisonReport(report);
    } catch (err) {
      console.error("Comparison error:", err);
      alert("Failed to run comparison. Ensure all selected ideas are completed.");
    } finally {
      setComparing(false);
    }
  };

  const isIdle = status === "idle" && !submitting;
  const isActive = status === "streaming" || status === "connecting" || comparing;
  const isDone = status === "completed" && !comparing;
  const isFailed = status === "failed";

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      {/* Input Section */}
      <AnimatePresence mode="wait">
        {(isIdle || isFailed) && (
          <motion.div
            key="input"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-6"
          >
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold mb-2 gradient-text">
                Validate Your Idea
              </h1>
              <p className="text-[var(--text-secondary)]">
                Describe your startup idea and let our AI agents analyze it in
                real-time.
              </p>
            </div>

            {isFailed && (
              <div className="flex items-center gap-2 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm">
                <XCircle className="w-4 h-4" />
                Validation failed. Please try again.
              </div>
            )}

            <div className="glass-card p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                  Your Idea *
                </label>
                <textarea
                  value={idea}
                  onChange={(e) => setIdea(e.target.value)}
                  className="input-dark min-h-[120px] resize-y glow-border"
                  placeholder="Describe your startup idea in detail — what problem it solves, who it's for, and how it works..."
                />
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  {idea.length}/2000 characters
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                    Target Market
                  </label>
                  <input
                    value={market}
                    onChange={(e) => setMarket(e.target.value)}
                    className="input-dark"
                    placeholder="e.g. B2B SaaS"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5">
                    Budget
                  </label>
                  <input
                    value={budget}
                    onChange={(e) => setBudget(e.target.value)}
                    className="input-dark"
                    placeholder="e.g. $10k"
                  />
                </div>
              </div>
              <button
                onClick={handleSubmit}
                disabled={idea.trim().length < 10 || submitting}
                className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-40"
              >
                {submitting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    Launch Validation
                  </>
                )}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Streaming Report */}
      {(isActive || isDone) && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {/* Status Bar */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              {isActive && (
                <div className="flex items-center gap-2 text-sm text-[var(--accent-violet)]">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{comparing ? "Running Head-to-Head Comparison..." : "Analyzing your idea…"}</span>
                </div>
              )}
              {isDone && (
                <div className="flex items-center gap-2 text-sm text-[var(--accent-emerald)]">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Validation Complete</span>
                </div>
              )}
            </div>
            <span className="text-xs text-[var(--text-muted)]">
              {sections.length} sections loaded
            </span>
          </div>

          {/* Sections */}
          <AnimatePresence mode="popLayout">
            {sections.map((section, i) => (
              <ReportSection key={section.section + i} section={section} index={i} />
            ))}
          </AnimatePresence>

          {/* Action Bar */}
          {isDone && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="glass-card p-4 flex items-center justify-center gap-3 mt-6"
            >
              <button onClick={handleExport} className="btn-ghost flex items-center gap-2">
                <FileDown className="w-4 h-4" />
                Export PDF
              </button>
              <button 
                onClick={() => setShowCompareSelect(true)} 
                className="btn-ghost flex items-center gap-2"
              >
                <GitCompare className="w-4 h-4" />
                Compare Ideas
              </button>
              <button
                onClick={() => setShowPublish(true)}
                className="btn-primary flex items-center gap-2"
              >
                <Upload className="w-4 h-4" />
                Publish to Arena
              </button>
            </motion.div>
          )}
        </motion.div>
      )}

      {/* Publish Modal */}
      <AnimatePresence>
        {showPublish && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="glass-card p-6 w-full max-w-md mx-4"
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold">Publish to Arena</h3>
                <button
                  onClick={() => setShowPublish(false)}
                  className="p-1 rounded-lg hover:bg-white/5"
                >
                  <X className="w-4 h-4 text-[var(--text-muted)]" />
                </button>
              </div>
              <p className="text-sm text-[var(--text-secondary)] mb-4">
                Give your idea a catchy title and tags so the community can find
                it.
              </p>
              <div className="space-y-3">
                <input
                  value={publishTitle}
                  onChange={(e) => setPublishTitle(e.target.value)}
                  className="input-dark"
                  placeholder="Title for your Arena post"
                  autoFocus
                />
                <input
                  value={publishTags}
                  onChange={(e) => setPublishTags(e.target.value)}
                  className="input-dark"
                  placeholder="Tags (comma-separated): SaaS, AI, B2B"
                />
                <button
                  onClick={handlePublish}
                  disabled={!publishTitle.trim() || publishing}
                  className="btn-primary w-full flex items-center justify-center gap-2 disabled:opacity-40"
                >
                  {publishing ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <Upload className="w-4 h-4" />
                      Publish
                    </>
                  )}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Compare Ideas Selection Modal */}
      <AnimatePresence>
        {showCompareSelect && validationId && (
          <CompareModal
            currentValidationId={validationId}
            onClose={() => setShowCompareSelect(false)}
            onCompare={handleRunComparison}
          />
        )}
      </AnimatePresence>

      {/* Comparison Results Modal */}
      <AnimatePresence>
        {comparisonReport && (
          <ComparisonReportModal
            report={comparisonReport}
            onClose={() => setComparisonReport(null)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

/* ─── Section Card ─── */
function ReportSection({ section, index }: { section: WSSection; index: number }) {
  const Icon = sectionIcons[section.section] || Sparkles;
  const label = sectionLabels[section.section] || section.section;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, delay: index * 0.05 }}
      className="glass-card p-6"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-xl bg-violet-500/10 flex items-center justify-center">
          <Icon className="w-4.5 h-4.5 text-[var(--accent-violet)]" />
        </div>
        <h3 className="font-semibold text-lg">{label}</h3>
      </div>
      <div className="text-sm text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
        {typeof section.data === "string"
          ? section.data
          : JSON.stringify(section.data, null, 2)}
      </div>
    </motion.div>
  );
}
