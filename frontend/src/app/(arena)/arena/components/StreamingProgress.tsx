"use client";
import { motion, AnimatePresence } from "framer-motion";
import {
  Loader2,
  Wifi,
  CheckCircle2,
  XCircle,
  Globe,
  Brain,
  DollarSign,
  BarChart3,
  Sparkles,
} from "lucide-react";

interface Stage {
  id: string;
  label: string;
  icon: React.ReactNode;
  status: "pending" | "active" | "completed";
}

const PIPELINE_STAGES: Omit<Stage, "status">[] = [
  { id: "firecrawl", label: "Firecrawling competitors...", icon: <Globe className="w-4 h-4" /> },
  { id: "pricing", label: "Analyzing pricing data...", icon: <DollarSign className="w-4 h-4" /> },
  { id: "sentiment", label: "Scanning market sentiment...", icon: <BarChart3 className="w-4 h-4" /> },
  { id: "gemini", label: "Running Gemini Consensus...", icon: <Brain className="w-4 h-4" /> },
  { id: "synthesis", label: "Synthesizing final report...", icon: <Sparkles className="w-4 h-4" /> },
];

interface StreamingProgressProps {
  completedSections: string[];
  status: "connecting" | "streaming" | "completed" | "failed";
}

export default function StreamingProgress({ completedSections, status }: StreamingProgressProps) {
  const getStageStatus = (stageId: string, index: number): Stage["status"] => {
    if (completedSections.includes(stageId)) return "completed";
    // The first non-completed stage is active
    const completedCount = PIPELINE_STAGES.filter((s) =>
      completedSections.includes(s.id)
    ).length;
    if (index === completedCount && status === "streaming") return "active";
    return "pending";
  };

  const progress = (completedSections.length / PIPELINE_STAGES.length) * 100;

  return (
    <div className="space-y-4">
      {/* Progress Bar */}
      <div className="relative h-2 bg-black/20 rounded-full overflow-hidden border border-[var(--border-subtle)]">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-[var(--accent-cyan)] to-[var(--accent-violet)] shadow-[0_0_12px_rgba(139,92,246,0.6)]"
          initial={{ width: 0 }}
          animate={{ width: `${status === "completed" ? 100 : progress}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
        {status === "streaming" && (
          <div className="absolute inset-0 progress-shimmer rounded-full" />
        )}
      </div>

      {/* Stages */}
      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {PIPELINE_STAGES.map((stage, index) => {
            const stageStatus = getStageStatus(stage.id, index);
            return (
              <motion.div
                key={stage.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-300 ${
                  stageStatus === "active"
                    ? "bg-cyan-500/10 border border-cyan-500/30 shadow-[0_0_15px_rgba(6,182,212,0.1)]"
                    : stageStatus === "completed"
                    ? "bg-emerald-500/[0.05] border border-emerald-500/10"
                    : "opacity-40 border border-transparent"
                }`}
              >
                {/* Status Icon */}
                <div className="shrink-0 flex items-center justify-center w-6 h-6">
                  {stageStatus === "completed" ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]" />
                  ) : stageStatus === "active" ? (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                    >
                      <Loader2 className="w-5 h-5 text-cyan-400 drop-shadow-[0_0_8px_rgba(6,182,212,0.3)]" />
                    </motion.div>
                  ) : (
                    <div className="w-4 h-4 rounded-full border-2 border-[var(--text-muted)]/40" />
                  )}
                </div>

                {/* Stage Icon */}
                <div
                  className={`flex items-center justify-center w-8 h-8 rounded-lg ${
                    stageStatus === "active"
                      ? "bg-cyan-500/15 text-cyan-400"
                      : stageStatus === "completed"
                      ? "bg-emerald-500/10 text-emerald-400"
                      : "bg-white/5 text-[var(--text-muted)]"
                  }`}
                >
                  {stage.icon}
                </div>

                {/* Label */}
                <span
                  className={`text-sm font-medium tracking-tight ${
                    stageStatus === "active"
                      ? "text-cyan-300 streaming-pulse"
                      : stageStatus === "completed"
                      ? "text-[var(--text-primary)]"
                      : "text-[var(--text-muted)]"
                  }`}
                >
                  {stageStatus === "completed"
                    ? stage.label.replace("...", " ✓")
                    : stage.label}
                </span>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Status Footer */}
      <AnimatePresence>
        {status === "failed" && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="flex items-center gap-2 text-sm font-medium text-[var(--accent-rose)] px-3 py-2 bg-rose-500/10 rounded-lg border border-rose-500/20"
          >
            <XCircle className="w-4 h-4" />
            <span>Pipeline failed — retrying...</span>
          </motion.div>
        )}
        {status === "connecting" && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="flex items-center gap-2 text-xs font-medium text-[var(--text-secondary)] px-3"
          >
            <Wifi className="w-4 h-4 streaming-pulse" />
            <span>Connecting to AI pipeline...</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
