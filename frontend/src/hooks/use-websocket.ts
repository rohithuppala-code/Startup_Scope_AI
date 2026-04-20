"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export interface WSSection {
  section: string;
  data: Record<string, unknown>;
}

interface UseWebSocketReturn {
  sections: WSSection[];
  status: "idle" | "connecting" | "streaming" | "completed" | "failed";
  connect: (validationId: string) => void;
  disconnect: () => void;
}

const WS_BASE =
  (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000")
    .replace("http://", "ws://")
    .replace("https://", "wss://");

export function useWebSocket(): UseWebSocketReturn {
  const [sections, setSections] = useState<WSSection[]>([]);
  const [status, setStatus] = useState<UseWebSocketReturn["status"]>("idle");
  const wsRef = useRef<WebSocket | null>(null);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const connect = useCallback(
    (validationId: string) => {
      disconnect();
      setSections([]);
      setStatus("connecting");

      const ws = new WebSocket(`${WS_BASE}/ws/validation/${validationId}`);
      wsRef.current = ws;

      ws.onopen = () => setStatus("streaming");

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.status === "completed") {
            setStatus("completed");
            // If the final message carries report data, add it
            if (msg.section) {
              setSections((prev) => [...prev, { section: msg.section, data: msg.data || msg }]);
            }
            return;
          }
          if (msg.status === "failed") {
            setStatus("failed");
            return;
          }

          // Progressive section update
          if (msg.section) {
            setSections((prev) => [...prev, { section: msg.section, data: msg.data || msg }]);
          }
        } catch {
          // Non-JSON frame, ignore
        }
      };

      ws.onerror = () => setStatus("failed");
      ws.onclose = () => {
        if (status !== "completed" && status !== "failed") {
          setStatus((s) => (s === "streaming" ? "completed" : s));
        }
      };
    },
    [disconnect, status]
  );

  useEffect(() => () => disconnect(), [disconnect]);

  return { sections, status, connect, disconnect };
}
