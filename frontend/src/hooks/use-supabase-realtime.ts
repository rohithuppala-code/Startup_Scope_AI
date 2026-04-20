"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import type { RealtimeChannel } from "@supabase/supabase-js";

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

  useEffect(() => {
    if (!channelId) return;

    // Fetch existing messages
    supabase
      .from("messages")
      .select("*")
      .eq("channel_id", channelId)
      .eq("is_hidden", false)
      .order("created_at", { ascending: true })
      .limit(100)
      .then(({ data }) => {
        if (data) setMessages(data as Message[]);
      });

    // Subscribe to realtime inserts
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
            setMessages((prev) => [...prev, newMsg]);
          }
        }
      )
      .subscribe((status) => {
        setIsConnected(status === "SUBSCRIBED");
      });

    channelRef.current = channel;

    return () => {
      channel.unsubscribe();
      channelRef.current = null;
      setIsConnected(false);
    };
  }, [channelId]);

  const sendMessage = useCallback(
    async (chId: string, userId: string, content: string) => {
      await supabase.from("messages").insert({
        channel_id: chId,
        user_id: userId,
        content,
        is_hidden: false,
      });
    },
    []
  );

  return { messages, sendMessage, isConnected };
}
