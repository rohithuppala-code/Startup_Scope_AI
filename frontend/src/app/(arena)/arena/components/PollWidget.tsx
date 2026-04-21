"use client";
import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import { BarChart3, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";

interface PollOption {
  id: string;
  text: string;
  votes?: number;
}

interface PollWidgetProps {
  pollId: string;
  postId: string;
  question: string;
  options: PollOption[];
  expiresAt?: string | null;
  totalVotes?: number;
  userVotedOptionId?: string | null;
}

export default function PollWidget({
  pollId,
  postId,
  question,
  options: initialOptions,
  expiresAt,
  totalVotes: initialTotal,
  userVotedOptionId: initialVote,
}: PollWidgetProps) {
  const userId = useUserStore((s) => s.userId);
  const [options, setOptions] = useState(initialOptions);
  const [votedOptionId, setVotedOptionId] = useState<string | null>(initialVote ?? null);
  const [totalVotes, setTotalVotes] = useState(initialTotal ?? 0);
  const [voting, setVoting] = useState(false);

  const hasVoted = votedOptionId !== null;
  const isExpired = expiresAt ? new Date(expiresAt) < new Date() : false;

  const handleVote = useCallback(
    async (optionId: string) => {
      if (hasVoted || voting || !userId || isExpired) return;
      setVoting(true);
      try {
        await api(`/api/v1/arena/posts/${postId}/polls/vote`, {
          method: "POST",
          userId,
          body: { poll_id: pollId, option_id: optionId },
        });
        setVotedOptionId(optionId);
        setTotalVotes((prev) => prev + 1);
        setOptions((prev) =>
          prev.map((o) =>
            o.id === optionId ? { ...o, votes: (o.votes ?? 0) + 1 } : o
          )
        );
      } catch (err) {
        console.error("[PollWidget] Vote error:", err);
      } finally {
        setVoting(false);
      }
    },
    [hasVoted, voting, userId, postId, pollId, isExpired]
  );

  return (
    <div className="space-y-2.5">
      {/* Question */}
      <div className="flex items-center gap-2 mb-1">
        <BarChart3 className="w-4 h-4 text-[var(--accent-violet)]" />
        <p className="text-sm font-medium text-[var(--text-primary)]">{question}</p>
      </div>

      {/* Options */}
      {options.map((option) => {
        const voteCount = option.votes ?? 0;
        const percentage = totalVotes > 0 ? Math.round((voteCount / totalVotes) * 100) : 0;
        const isVoted = votedOptionId === option.id;

        return (
          <motion.button
            key={option.id}
            whileHover={!hasVoted ? { scale: 1.01 } : {}}
            whileTap={!hasVoted ? { scale: 0.99 } : {}}
            onClick={() => handleVote(option.id)}
            disabled={hasVoted || isExpired}
            className={`poll-option w-full text-left ${isVoted ? "poll-option-voted" : ""}`}
          >
            {/* Background bar */}
            {hasVoted && (
              <div
                className="poll-option-bar"
                style={{ transform: `scaleX(${percentage / 100})` }}
              />
            )}

            <div className="relative flex items-center justify-between gap-2 z-10">
              <div className="flex items-center gap-2">
                {isVoted && <CheckCircle2 className="w-3.5 h-3.5 text-[var(--accent-violet)]" />}
                <span className="text-sm text-[var(--text-primary)]">{option.text}</span>
              </div>
              {hasVoted && (
                <span className="text-xs font-bold text-[var(--text-secondary)] tabular-nums">
                  {percentage}%
                </span>
              )}
            </div>
          </motion.button>
        );
      })}

      {/* Footer */}
      <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)] pt-1">
        <span>{totalVotes} vote{totalVotes !== 1 ? "s" : ""}</span>
        {isExpired && <span className="text-[var(--accent-rose)]">Poll ended</span>}
        {expiresAt && !isExpired && (
          <span>Ends {new Date(expiresAt).toLocaleDateString()}</span>
        )}
      </div>
    </div>
  );
}
