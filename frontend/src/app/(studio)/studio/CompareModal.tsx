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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="glass-card w-full max-w-2xl flex flex-col max-h-[80vh]"
      >
        <div className="p-5 border-b border-white/5 flex items-center justify-between shrink-0">
          <div>
            <h3 className="text-lg font-bold flex items-center gap-2">
              <GitCompare className="w-5 h-5 text-[var(--accent-violet)]" />
              Compare Ideas
            </h3>
            <p className="text-sm text-[var(--text-secondary)] mt-1">
              Select up to 10 completed validations to compare head-to-head.
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/5 text-[var(--text-muted)] hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-[var(--text-muted)]">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              Loading your ideas...
            </div>
          ) : validations.length < 2 ? (
            <div className="text-center py-10 text-[var(--text-muted)]">
              You need at least 2 completed validations to compare.
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
                  className={`p-4 rounded-xl border transition-all cursor-pointer flex items-start gap-4 ${
                    isSelected
                      ? "bg-violet-500/10 border-violet-500/30"
                      : "bg-black/20 border-white/5 hover:border-white/10"
                  } ${isCurrent ? "opacity-75 cursor-default" : ""}`}
                >
                  <div className="pt-1">
                    {isSelected ? (
                      <CheckCircle2 className="w-5 h-5 text-violet-400" />
                    ) : (
                      <div className="w-5 h-5 rounded-full border-2 border-[var(--text-muted)]" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm line-clamp-2 leading-relaxed">
                      {val.idea_description}
                    </p>
                    <div className="flex items-center gap-4 mt-2 text-xs text-[var(--text-muted)]">
                      <span>{new Date(val.created_at).toLocaleDateString()}</span>
                      {score && (
                        <span className="flex items-center gap-1 text-emerald-400/80">
                          Score: {score}
                        </span>
                      )}
                      {isCurrent && (
                        <span className="text-violet-400 font-medium">Current Validation</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="p-5 border-t border-white/5 bg-black/20 shrink-0 flex items-center justify-between">
          <span className="text-sm text-[var(--text-muted)]">
            {selected.size} / 10 selected
          </span>
          <button
            onClick={() => onCompare(Array.from(selected))}
            disabled={selected.size < 2}
            className="btn-primary flex items-center gap-2 disabled:opacity-50"
          >
            <GitCompare className="w-4 h-4" />
            Run Comparison
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
