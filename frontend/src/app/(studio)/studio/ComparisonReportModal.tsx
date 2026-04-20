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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        className="glass-card w-full max-w-4xl flex flex-col max-h-[90vh]"
      >
        <div className="p-6 border-b border-white/5 flex items-center justify-between shrink-0">
          <div>
            <h3 className="text-xl font-bold flex items-center gap-2">
              <Trophy className="w-6 h-6 text-yellow-500" />
              Idea Comparison Analysis
            </h3>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/5 text-[var(--text-muted)] hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-8">
          
          {/* Winners Section */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {report.winners?.map((winner: any, i: number) => {
              const icons: any = {
                market_size: Target,
                technical_difficulty: AlertTriangle,
                capital_efficiency: DollarSign,
                competitive_density: TrendingUp,
              };
              const Icon = icons[winner.dimension] || Trophy;
              return (
                <div key={i} className="glass-card p-4 bg-gradient-to-br from-violet-500/10 to-fuchsia-500/5">
                  <div className="flex items-center gap-2 mb-2 text-[var(--accent-violet)] text-sm font-semibold uppercase tracking-wider">
                    <Icon className="w-4 h-4" />
                    {winner.dimension.replace("_", " ")}
                  </div>
                  <div className="font-medium text-sm mb-1">{winner.winner_summary}</div>
                  <div className="text-xs text-[var(--text-muted)] leading-relaxed">{winner.reasoning}</div>
                </div>
              );
            })}
          </div>

          {/* Ideas Table */}
          <div className="glass-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-white/5 text-[var(--text-muted)]">
                  <tr>
                    <th className="p-4 font-medium">Idea</th>
                    <th className="p-4 font-medium text-center">Market Size</th>
                    <th className="p-4 font-medium text-center">Tech Difficulty</th>
                    <th className="p-4 font-medium text-center">Capital Eff.</th>
                    <th className="p-4 font-medium text-center">Comp. Density</th>
                    <th className="p-4 font-medium text-center text-emerald-400">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {report.ideas?.map((idea: any) => (
                    <tr key={idea.validation_id} className="hover:bg-white/5 transition-colors">
                      <td className="p-4 font-medium line-clamp-2 max-w-xs leading-relaxed">{idea.idea_summary}</td>
                      <td className="p-4 text-center tabular-nums">{idea.market_size}/100</td>
                      <td className="p-4 text-center tabular-nums">{idea.technical_difficulty}/100</td>
                      <td className="p-4 text-center tabular-nums">{idea.capital_efficiency}/100</td>
                      <td className="p-4 text-center tabular-nums">{idea.competitive_density}/100</td>
                      <td className="p-4 text-center tabular-nums font-bold text-emerald-400">{idea.overall_score}/100</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Narrative & Recommendation */}
          <div className="grid md:grid-cols-2 gap-6">
            <div className="glass-card p-5 bg-black/20">
              <h4 className="font-semibold text-lg mb-3">Strategic Narrative</h4>
              <div className="text-sm text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
                {report.narrative}
              </div>
            </div>
            <div className="glass-card p-5 border border-emerald-500/30 bg-emerald-500/5">
              <h4 className="font-semibold text-lg mb-3 flex items-center gap-2 text-emerald-400">
                <CheckCircle2 className="w-5 h-5" />
                Final Recommendation
              </h4>
              <div className="text-sm text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
                {report.recommendation}
              </div>
            </div>
          </div>

        </div>
      </motion.div>
    </motion.div>
  );
}
