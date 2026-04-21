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
    <div className="space-y-3">
      {/* Progress Bar */}
      <div className="relative h-1.5 bg-white/5 rounded-full overflow-hidden">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-cyan-500 to-violet-500"
          initial={{ width: 0 }}
          animate={{ width: `${status === "completed" ? 100 : progress}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
        {status === "streaming" && (
          <div className="absolute inset-0 progress-shimmer rounded-full" />
        )}
      </div>

      {/* Stages */}
      <div className="space-y-1.5">
        <AnimatePresence mode="popLayout">
          {PIPELINE_STAGES.map((stage, index) => {
            const stageStatus = getStageStatus(stage.id, index);
            return (
              <motion.div
                key={stage.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-all duration-300 ${
                  stageStatus === "active"
                    ? "bg-cyan-500/8 border border-cyan-500/20"
                    : stageStatus === "completed"
                    ? "bg-emerald-500/5"
                    : "opacity-40"
                }`}
              >
                {/* Status Icon */}
                <div className="shrink-0">
                  {stageStatus === "completed" ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : stageStatus === "active" ? (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                    >
                      <Loader2 className="w-4 h-4 text-cyan-400" />
                    </motion.div>
                  ) : (
                    <div className="w-4 h-4 rounded-full border border-white/10" />
                  )}
                </div>

                {/* Stage Icon */}
                <div
                  className={
                    stageStatus === "active"
                      ? "text-cyan-400"
                      : stageStatus === "completed"
                      ? "text-emerald-400"
                      : "text-[var(--text-muted)]"
                  }
                >
                  {stage.icon}
                </div>

                {/* Label */}
                <span
                  className={`text-xs font-medium ${
                    stageStatus === "active"
                      ? "text-cyan-300 streaming-pulse"
                      : stageStatus === "completed"
                      ? "text-[var(--text-secondary)]"
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
      {status === "failed" && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 text-xs text-[var(--accent-rose)] px-3"
        >
          <XCircle className="w-3.5 h-3.5" />
          <span>Pipeline failed — retrying...</span>
        </motion.div>
      )}
      {status === "connecting" && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center gap-2 text-xs text-[var(--text-muted)] px-3"
        >
          <Wifi className="w-3.5 h-3.5 streaming-pulse" />
          <span>Connecting to AI pipeline...</span>
        </motion.div>
      )}
    </div>
  );
}
