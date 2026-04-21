import { useState } from "react";
import { motion } from "framer-motion";
import { BarChart3, Check } from "lucide-react";

export function GroupPollCard({ payload, messageId, votes, onVote, currentUserId }: any) {
  // votes is an array of objects: { user_id, option_idx }
  const totalVotes = votes.length;
  
  // Find if current user voted
  const myVote = votes.find((v: any) => v.user_id === currentUserId)?.option_idx;

  return (
    <div className="w-[300px] max-w-full glass-card p-3 pointer-events-auto border-violet-500/30 border">
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="w-4 h-4 text-violet-400" />
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
              className={`w-full relative overflow-hidden rounded-lg p-2.5 text-left transition-all ${
                isSelected ? "bg-violet-500/20 border border-violet-500/40" : "bg-black/20 hover:bg-black/40 border border-transparent"
              }`}
            >
              <div
                className="absolute inset-0 bg-violet-500/10 origin-left transition-transform duration-500 ease-out"
                style={{ transform: `scaleX(${percentage / 100})` }}
              />
              <div className="relative flex items-center justify-between z-10">
                <div className="flex items-center gap-2">
                  <div className={`w-4 h-4 rounded-full border flex items-center justify-center ${isSelected ? "border-violet-400 bg-violet-400 text-white" : "border-[var(--border-subtle)]"}`}>
                    {isSelected && <Check className="w-3 h-3" />}
                  </div>
                  <span className="text-sm text-[var(--text-primary)]">{opt}</span>
                </div>
                <span className="text-xs text-[var(--text-muted)] font-medium">{percentage}%</span>
              </div>
            </button>
          );
        })}
      </div>
      
      <div className="mt-3 text-[10px] text-[var(--text-muted)] text-right">
        {totalVotes} {totalVotes === 1 ? 'vote' : 'votes'}
      </div>
    </div>
  );
}
