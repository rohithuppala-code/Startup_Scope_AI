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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function useWebSocket(): UseWebSocketReturn {
  const [sections, setSections] = useState<WSSection[]>([]);
  const [status, setStatus] = useState<UseWebSocketReturn["status"]>("idle");
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const validationIdRef = useRef<string | null>(null);
  const attemptRef = useRef(0);

  const disconnect = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    validationIdRef.current = null;
  }, []);

  const connect = useCallback(
    (validationId: string) => {
      disconnect();
      setSections([]);
      setStatus("connecting");
      validationIdRef.current = validationId;
      attemptRef.current = 0;

      // Poll the validation status REST endpoint instead of using WebSocket
      intervalRef.current = setInterval(async () => {
        const vid = validationIdRef.current;
        if (!vid) return;

        attemptRef.current += 1;

        // Stop polling after 3 minutes (90 × 2s intervals)
        if (attemptRef.current > 90) {
          setStatus("failed");
          disconnect();
          return;
        }

        try {
          // The main backend's GET /api/v1/validate/{id} returns status + report_json.
          // It requires x-user-id but for the group chat we won't know the creator's id,
          // so we fetch WITHOUT it (use service-role-aware endpoint if available, else best-effort).
          const res = await fetch(`${API_BASE}/api/v1/validate/${vid}/status`).catch(
            () => fetch(`${API_BASE}/api/v1/validate/${vid}`)
          );
          if (!res.ok) return; // keep polling if not ready

          const data = await res.json() as {
            status: string;
            report_json?: Record<string, unknown>;
            idea_description?: string;
          };

          if (data.status === "completed") {
            setStatus("completed");
            if (data.report_json) {
              setSections([{ section: "report", data: data.report_json }]);
            }
            disconnect();
          } else if (data.status === "failed") {
            setStatus("failed");
            disconnect();
          } else {
            // Still processing — mark as streaming so the card shows the spinner
            setStatus("streaming");
          }
        } catch {
          // Network blip — keep polling
        }
      }, 2000);
    },
    [disconnect]
  );

  useEffect(() => () => disconnect(), [disconnect]);

  return { sections, status, connect, disconnect };
}
