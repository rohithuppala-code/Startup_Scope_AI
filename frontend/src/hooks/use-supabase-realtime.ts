"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import type { RealtimeChannel } from "@supabase/supabase-js";
import { api } from "@/lib/api";
import { useUserStore } from "@/stores/user-store";

interface Message {
  id: string;
  channel_id: string;
  user_id: string;
  content: string;
  created_at: string;
  is_hidden: boolean;
}

interface UseSupabaseRealtimeReturn {
  messages: Message[];
  sendMessage: (channelId: string, userId: string, content: string) => Promise<void>;
  isConnected: boolean;
}

export function useSupabaseRealtime(channelId: string | null): UseSupabaseRealtimeReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const channelRef = useRef<RealtimeChannel | null>(null);
  const hasFetchedRef = useRef(false);

  useEffect(() => {
    if (!channelId) return;
    hasFetchedRef.current = false;

    const accessToken = useUserStore.getState().accessToken;
    const userId = useUserStore.getState().userId;

    if (accessToken) {
      supabase.realtime.setAuth(accessToken);
    }

    // Initial fetch — only once per channel mount
    if (userId) {
      api<Message[]>(`/api/v1/channels/${channelId}/messages?limit=100`, { userId })
        .then((data) => {
          if (data) {
            setMessages(data);
            hasFetchedRef.current = true;
          }
        })
        .catch(console.error);
    }

    // Slow background poll — 15s — purely as a safety net for dropped WS events
    const pollInterval = setInterval(() => {
      if (userId && hasFetchedRef.current) {
        api<Message[]>(`/api/v1/channels/${channelId}/messages?limit=100`, { userId })
          .then((data) => {
            if (data) {
              setMessages((prev) => {
                // Only update if there are actually new messages
                if (data.length !== prev.length || data[data.length - 1]?.id !== prev[prev.length - 1]?.id) {
                  return data;
                }
                return prev;
              });
            }
          })
          .catch(console.error);
      }
    }, 15000); // 15 seconds — not 2 seconds

    // Subscribe to realtime inserts (this is the PRIMARY delivery mechanism)
    const channel = supabase
      .channel(`messages:${channelId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "messages",
          filter: `channel_id=eq.${channelId}`,
        },
        (payload) => {
          const newMsg = payload.new as Message;
          if (!newMsg.is_hidden) {
            setMessages((prev) => {
              // Deduplicate — prevent double-append from optimistic + realtime
              if (prev.some((m) => m.id === newMsg.id)) return prev;
              return [...prev, newMsg];
            });
          }
        }
      )
      .subscribe((status) => {
        setIsConnected(status === "SUBSCRIBED");
      });

    channelRef.current = channel;

    return () => {
      clearInterval(pollInterval);
      channel.unsubscribe();
      channelRef.current = null;
      setIsConnected(false);
    };
  }, [channelId]);

  const sendMessage = useCallback(
    async (chId: string, userId: string, content: string) => {
      const state = useUserStore.getState();
      await api("/api/v1/messages", {
        method: "POST",
        body: { channel_id: chId, content },
        userId: state.userId || userId,
      });
    },
    []
  );

  return { messages, sendMessage, isConnected };
}
