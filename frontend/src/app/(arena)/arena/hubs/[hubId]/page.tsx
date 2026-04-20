"use client";
import { useSearchParams } from "next/navigation";
import { useState, useRef, useEffect, Suspense } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useSupabaseRealtime } from "@/hooks/use-supabase-realtime";
import { useUserStore } from "@/stores/user-store";
import { Send, Wifi, WifiOff, Hash } from "lucide-react";
import { formatDate } from "@/lib/utils";

function ChatContent() {
  const searchParams = useSearchParams();
  const channelId = searchParams.get("channel");
  const userId = useUserStore((s) => s.userId);
  const { messages, sendMessage, isConnected } =
    useSupabaseRealtime(channelId);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || !channelId || !userId) return;
    const text = input.trim();
    setInput("");
    await sendMessage(channelId, userId, text);
  };

  if (!channelId) {
    return (
      <div className="flex-1 flex items-center justify-center text-[var(--text-muted)]">
        <div className="text-center">
          <Hash className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p>Select a channel to start chatting</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Connection status */}
      <div className="shrink-0 px-4 py-2 border-b border-[var(--border-subtle)] flex items-center gap-2 text-xs">
        {isConnected ? (
          <span className="flex items-center gap-1.5 text-emerald-400">
            <Wifi className="w-3 h-3" />
            Connected — Live
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-amber-400">
            <WifiOff className="w-3 h-3" />
            Connecting…
          </span>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <AnimatePresence mode="popLayout">
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-3 ${
                msg.user_id === userId ? "justify-end" : ""
              }`}
            >
              {msg.user_id !== userId && (
                <div className="w-8 h-8 rounded-full bg-violet-600/20 flex items-center justify-center shrink-0 text-xs font-bold text-violet-300">
                  {msg.user_id.charAt(0).toUpperCase()}
                </div>
              )}
              <div
                className={`max-w-[70%] rounded-2xl px-4 py-2.5 text-sm ${
                  msg.user_id === userId
                    ? "bg-violet-600/20 border border-violet-500/20 text-[var(--text-primary)]"
                    : "bg-[var(--bg-card)] border border-[var(--border-subtle)] text-[var(--text-secondary)]"
                }`}
              >
                <p>{msg.content}</p>
                <p className="text-[10px] text-[var(--text-muted)] mt-1">
                  {formatDate(msg.created_at)}
                </p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 p-4 border-t border-[var(--border-subtle)]">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            className="input-dark flex-1"
            placeholder="Type a message…"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="btn-primary px-4 disabled:opacity-30"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function HubChatPage() {
  return (
    <Suspense
      fallback={
        <div className="flex-1 flex items-center justify-center text-[var(--text-muted)]">
          Loading…
        </div>
      }
    >
      <ChatContent />
    </Suspense>
  );
}
