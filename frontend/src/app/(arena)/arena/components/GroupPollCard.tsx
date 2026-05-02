import { useState } from "react";
import { motion } from "framer-motion";
import { BarChart3, Check } from "lucide-react";

export function GroupPollCard({ payload, messageId, votes, onVote, currentUserId }: any) {
  // votes is an array of objects: { user_id, option_idx }
  const totalVotes = votes.length;
  
  // Find if current user voted
  const myVote = votes.find((v: any) => v.user_id === currentUserId)?.option_idx;

  return (
    <div className="w-[300px] max-w-full glass-card p-4 pointer-events-auto">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-violet-500/10 flex items-center justify-center shrink-0">
          <BarChart3 className="w-4 h-4 text-[var(--accent-violet)]" />
        </div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] leading-tight">{payload.question}</h3>
      </div>
      
      <div className="space-y-2">
        {payload.options.map((opt: string, i: number) => {
          const optVotes = votes.filter((v: any) => v.option_idx === i).length;
          const percentage = totalVotes === 0 ? 0 : Math.round((optVotes / totalVotes) * 100);
          const isSelected = myVote === i;

          return (
            <button
              key={i}
              onClick={() => onVote(i)}
              className={`w-full relative overflow-hidden rounded-xl p-3 text-left transition-all ${
                isSelected 
                  ? "bg-[var(--accent-violet)]/10 border border-[var(--accent-violet)]/40 shadow-[0_0_12px_rgba(139,92,246,0.1)]" 
                  : "bg-black/20 hover:bg-black/40 border border-[var(--border-subtle)] hover:border-white/10"
              }`}
            >
              <div
                className="absolute inset-0 bg-gradient-to-r from-[var(--accent-violet)]/15 to-[var(--accent-violet)]/5 origin-left transition-transform duration-700 ease-out"
                style={{ transform: `scaleX(${percentage / 100})` }}
              />
              <div className="relative flex items-center justify-between z-10">
                <div className="flex items-center gap-2.5">
                  <div className={`w-4 h-4 rounded-full border flex items-center justify-center transition-colors ${
                    isSelected 
                      ? "border-[var(--accent-violet)] bg-[var(--accent-violet)] text-white" 
                      : "border-[var(--text-muted)] bg-transparent"
                  }`}>
                    {isSelected && <Check className="w-3 h-3" />}
                  </div>
                  <span className={`text-sm font-medium ${isSelected ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                    {opt}
                  </span>
                </div>
                <span className={`text-xs font-bold tabular-nums ${isSelected ? "text-[var(--accent-violet)]" : "text-[var(--text-muted)]"}`}>
                  {percentage}%
                </span>
              </div>
            </button>
          );
        })}
      </div>
      
      <div className="mt-4 pt-3 border-t border-[var(--border-subtle)] text-[10px] text-[var(--text-muted)] flex justify-between items-center">
        <span>Public Poll</span>
        <span className="font-medium">{totalVotes} {totalVotes === 1 ? 'vote' : 'votes'}</span>
      </div>
    </div>
  );
}
