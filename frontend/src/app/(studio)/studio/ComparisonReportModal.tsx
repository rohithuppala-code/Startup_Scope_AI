"use client";
import { motion } from "framer-motion";
import { X, Trophy, AlertTriangle, TrendingUp, DollarSign, Target, CheckCircle2 } from "lucide-react";

export function ComparisonReportModal({
  report,
  onClose,
}: {
  report: any;
  onClose: () => void;
}) {
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
        className="glass-card noise-overlay w-full max-w-4xl flex flex-col max-h-[90vh] shadow-2xl border-white/10"
      >
        <div className="p-6 border-b border-[var(--border-subtle)] flex items-center justify-between shrink-0 bg-black/20">
          <div>
            <h3 className="text-2xl font-bold flex items-center gap-2.5 text-[var(--text-primary)] tracking-tight">
              <Trophy className="w-6 h-6 text-yellow-500 drop-shadow-[0_0_8px_rgba(234,179,8,0.5)]" />
              Idea Comparison Analysis
            </h3>
          </div>
          <button onClick={onClose} className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-[var(--text-muted)] hover:text-white transition-all shadow-sm">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 md:p-8 space-y-8 scroll-smooth">
          
          {/* Winners Section */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
            {report.winners?.map((winner: any, i: number) => {
              const icons: any = {
                market_size: Target,
                technical_difficulty: AlertTriangle,
                capital_efficiency: DollarSign,
                competitive_density: TrendingUp,
              };
              const Icon = icons[winner.dimension] || Trophy;
              return (
                <div key={i} className="glass-card p-5 bg-gradient-to-br from-violet-500/10 to-fuchsia-500/5 border-[var(--border-subtle)] hover:border-violet-500/30 transition-all">
                  <div className="flex items-center gap-2 mb-3 text-[var(--accent-violet)] text-xs font-bold uppercase tracking-widest bg-violet-500/10 w-fit px-2.5 py-1 rounded-md">
                    <Icon className="w-4 h-4" />
                    {winner.dimension.replace("_", " ")}
                  </div>
                  <div className="font-semibold text-[15px] mb-2 text-[var(--text-primary)] tracking-tight">{winner.winner_summary}</div>
                  <div className="text-sm text-[var(--text-muted)] leading-relaxed">{winner.reasoning}</div>
                </div>
              );
            })}
          </div>

          {/* Ideas Table */}
          <div className="glass-card overflow-hidden border-[var(--border-subtle)] shadow-md">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm whitespace-nowrap md:whitespace-normal">
                <thead className="bg-black/40 text-[var(--text-muted)] border-b border-[var(--border-subtle)]">
                  <tr>
                    <th className="p-5 font-semibold uppercase tracking-wider text-xs">Idea</th>
                    <th className="p-5 font-semibold uppercase tracking-wider text-xs text-center">Market Size</th>
                    <th className="p-5 font-semibold uppercase tracking-wider text-xs text-center">Tech Difficulty</th>
                    <th className="p-5 font-semibold uppercase tracking-wider text-xs text-center">Capital Eff.</th>
                    <th className="p-5 font-semibold uppercase tracking-wider text-xs text-center">Comp. Density</th>
                    <th className="p-5 font-bold uppercase tracking-wider text-xs text-center text-emerald-400 bg-emerald-500/5">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)] bg-black/10">
                  {report.ideas?.map((idea: any) => (
                    <tr key={idea.validation_id} className="hover:bg-white/[0.02] transition-colors">
                      <td className="p-5 font-medium text-[15px] text-[var(--text-primary)] line-clamp-2 max-w-xs md:max-w-sm leading-relaxed" title={idea.idea_summary}>{idea.idea_summary}</td>
                      <td className="p-5 text-center font-mono text-[var(--text-secondary)]">{idea.market_size}/100</td>
                      <td className="p-5 text-center font-mono text-[var(--text-secondary)]">{idea.technical_difficulty}/100</td>
                      <td className="p-5 text-center font-mono text-[var(--text-secondary)]">{idea.capital_efficiency}/100</td>
                      <td className="p-5 text-center font-mono text-[var(--text-secondary)]">{idea.competitive_density}/100</td>
                      <td className="p-5 text-center font-mono font-bold text-emerald-400 bg-emerald-500/5">{idea.overall_score}/100</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Narrative & Recommendation */}
          <div className="grid md:grid-cols-2 gap-6">
            <div className="glass-card p-6 bg-black/20 border-[var(--border-subtle)]">
              <h4 className="font-bold text-lg mb-4 text-[var(--text-primary)] tracking-tight">Strategic Narrative</h4>
              <div className="text-[15px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
                {report.narrative}
              </div>
            </div>
            <div className="glass-card p-6 border border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 to-transparent shadow-[inset_0_0_20px_rgba(16,185,129,0.05)]">
              <h4 className="font-bold text-lg mb-4 flex items-center gap-2.5 text-emerald-400 tracking-tight">
                <CheckCircle2 className="w-5 h-5 drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]" />
                Final Recommendation
              </h4>
              <div className="text-[15px] text-[var(--text-primary)] font-medium leading-relaxed whitespace-pre-wrap">
                {report.recommendation}
              </div>
            </div>
          </div>

        </div>
      </motion.div>
    </motion.div>
  );
}
