"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { X, Loader2, GitCompare, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";

export function CompareModal({
  currentValidationId,
  onClose,
  onCompare,
}: {
  currentValidationId: string;
  onClose: () => void;
  onCompare: (ids: string[]) => void;
}) {
  const { userId } = useAuth();
  const [validations, setValidations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set([currentValidationId]));

  useEffect(() => {
    if (!userId) return;
    api<any[]>("/api/v1/validations?status=completed", { userId })
      .then((data) => setValidations(data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [userId]);

  const toggleSelect = (id: string) => {
    if (id === currentValidationId) return; // Always selected
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else if (next.size < 10) next.add(id);
    setSelected(next);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4 sm:p-6"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 10 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.95, opacity: 0, y: 10 }}
        className="glass-card noise-overlay w-full max-w-2xl flex flex-col max-h-[85vh] shadow-2xl border-white/10"
      >
        <div className="p-6 border-b border-[var(--border-subtle)] flex items-center justify-between shrink-0 bg-black/20">
          <div>
            <h3 className="text-xl font-bold flex items-center gap-2 text-[var(--text-primary)] tracking-tight">
              <GitCompare className="w-5 h-5 text-[var(--accent-violet)]" />
              Compare Ideas
            </h3>
            <p className="text-sm font-medium text-[var(--text-secondary)] mt-1.5">
              Select up to 10 completed validations to compare head-to-head.
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-[var(--text-muted)] hover:text-white transition-all shadow-sm">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 text-[var(--text-muted)]">
              <Loader2 className="w-8 h-8 animate-spin mb-4 text-[var(--accent-violet)]" />
              <p className="text-sm font-medium">Loading your ideas...</p>
            </div>
          ) : validations.length < 2 ? (
            <div className="text-center py-16 text-[var(--text-muted)] glass-card border-dashed">
              <GitCompare className="w-10 h-10 mx-auto mb-3 opacity-50" />
              <p className="text-[15px] font-semibold text-[var(--text-primary)] tracking-tight">Not enough validations</p>
              <p className="text-sm mt-1">You need at least 2 completed validations to compare.</p>
            </div>
          ) : (
            validations.map((val) => {
              const isSelected = selected.has(val.id);
              const isCurrent = val.id === currentValidationId;
              const score = val.report_json?.feasibility_score;

              return (
                <div
                  key={val.id}
                  onClick={() => toggleSelect(val.id)}
                  className={`p-5 rounded-2xl border transition-all cursor-pointer flex items-start gap-4 ${
                    isSelected
                      ? "bg-violet-500/10 border-violet-500/40 shadow-[inset_0_0_20px_rgba(139,92,246,0.1)]"
                      : "bg-black/20 border-[var(--border-subtle)] hover:border-white/20 hover:bg-black/30"
                  } ${isCurrent ? "opacity-80 cursor-default" : ""}`}
                >
                  <div className="pt-1.5 shrink-0">
                    {isSelected ? (
                      <CheckCircle2 className="w-5 h-5 text-violet-400 drop-shadow-[0_0_8px_rgba(139,92,246,0.5)]" />
                    ) : (
                      <div className="w-5 h-5 rounded-full border-2 border-[var(--text-muted)]/50" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className={`font-semibold text-[15px] line-clamp-2 leading-relaxed tracking-tight ${isSelected ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                      {val.idea_description}
                    </p>
                    <div className="flex flex-wrap items-center gap-3 mt-3 text-xs font-medium text-[var(--text-muted)]">
                      <span className="bg-white/5 px-2 py-1 rounded-md">{new Date(val.created_at).toLocaleDateString()}</span>
                      {score && (
                        <span className="flex items-center gap-1 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-1 rounded-md">
                          Score: {score}
                        </span>
                      )}
                      {isCurrent && (
                        <span className="text-violet-400 bg-violet-500/10 border border-violet-500/20 px-2 py-1 rounded-md">Current Validation</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="p-6 border-t border-[var(--border-subtle)] bg-black/40 shrink-0 flex items-center justify-between backdrop-blur-md">
          <span className="text-sm font-semibold text-[var(--text-muted)]">
            <span className="text-[var(--text-primary)]">{selected.size}</span> / 10 selected
          </span>
          <button
            onClick={() => onCompare(Array.from(selected))}
            disabled={selected.size < 2}
            className="btn-primary py-2.5 px-6 flex items-center gap-2 disabled:opacity-50 font-semibold shadow-lg shadow-violet-500/20"
          >
            <GitCompare className="w-4 h-4" />
            Run Comparison
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
