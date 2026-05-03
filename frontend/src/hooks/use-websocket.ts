"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useUserStore } from "@/stores/user-store";

export interface WSSection {
  section: string;
  data: Record<string, unknown> | string;
}

interface UseWebSocketReturn {
  sections: WSSection[];
  rawReport: Record<string, unknown> | null; // Full report_json — used by LiveIdeaCard
  status: "idle" | "connecting" | "streaming" | "completed" | "failed";
  connect: (validationId: string) => void;
  disconnect: () => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

const KNOWN_SECTIONS = [
  "market_analysis",
  "competitor_analysis",
  "pricing",
  "patents",
  "consensus",
  "recommendation",
  "funding",
  "sentiment",
  "jobs",
  "traffic",
] as const;

/**
 * Flattens a report_json object into named WSSection cards.
 * Known sections are emitted first in canonical order; unknown keys follow.
 */
function flattenReportJson(reportJson: Record<string, unknown>): WSSection[] {
  const sections: WSSection[] = [];

  for (const key of KNOWN_SECTIONS) {
    if (key in reportJson) {
      const val = reportJson[key];
      sections.push({
        section: key,
        data:
          typeof val === "object" && val !== null
            ? (val as Record<string, unknown>)
            : { value: String(val) },
      });
    }
  }

  // Emit any remaining top-level keys not in KNOWN_SECTIONS
  for (const [key, val] of Object.entries(reportJson)) {
    if (!(KNOWN_SECTIONS as readonly string[]).includes(key)) {
      sections.push({
        section: key,
        data:
          typeof val === "object" && val !== null
            ? (val as Record<string, unknown>)
            : { value: String(val) },
      });
    }
  }

  return sections;
}

export function useWebSocket(): UseWebSocketReturn {
  const [sections, setSections] = useState<WSSection[]>([]);
  const [rawReport, setRawReport] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState<UseWebSocketReturn["status"]>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const fallbackIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const validationIdRef = useRef<string | null>(null);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (fallbackIntervalRef.current) {
      clearInterval(fallbackIntervalRef.current);
      fallbackIntervalRef.current = null;
    }
    validationIdRef.current = null;
  }, []);

  const startFallbackPolling = useCallback((vid: string) => {
    if (fallbackIntervalRef.current) return;
    
    let attempt = 0;
    fallbackIntervalRef.current = setInterval(async () => {
      attempt += 1;
      if (attempt > 150) {
        setStatus("failed");
        disconnect();
        return;
      }

      try {
        const userId = useUserStore.getState().userId;
        const accessToken = useUserStore.getState().accessToken;
        const headers: Record<string, string> = {};
        if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
        else if (userId) headers["x-user-id"] = userId;
        
        const res = await fetch(`${API_BASE}/api/v1/validate/${vid}/status`).catch(
          () => fetch(`${API_BASE}/api/v1/validate/${vid}`, { headers })
        );
        if (!res.ok) return;

        const data = await res.json();
        if (data.status === "completed") {
          setStatus("completed");
          if (data.report_json) {
            setRawReport(data.report_json);
            setSections(flattenReportJson(data.report_json));
          }
          disconnect();
        } else if (data.status === "failed") {
          setStatus("failed");
          disconnect();
        } else {
          setStatus("streaming");
        }
      } catch (err) {}
    }, 2000);
  }, [disconnect]);

  const connect = useCallback(
    (validationId: string) => {
      disconnect();
      setSections([]);
      setRawReport(null);
      setStatus("connecting");
      validationIdRef.current = validationId;

      const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsHost = API_BASE.replace(/^https?:\/\//, "");
      const wsUrl = `${wsProtocol}//${wsHost}/ws/validation/${validationId}`;

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setStatus("streaming");
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.status === "failed") {
              setStatus("failed");
              disconnect();
              return;
            }

            if (data.status === "completed") {
              setStatus("completed");
              if (data.report_json) {
                setRawReport(data.report_json);
                setSections(flattenReportJson(data.report_json));
              }
              disconnect();
              return;
            }

            if (data.section && data.data) {
              setSections((prev) => {
                const exists = prev.findIndex((s) => s.section === data.section);
                if (exists >= 0) {
                  const updated = [...prev];
                  updated[exists] = { section: data.section, data: data.data };
                  return updated;
                }
                return [...prev, { section: data.section, data: data.data }];
              });
            }
          } catch (e) {
            console.error("Failed to parse WS message", e);
          }
        };

        ws.onerror = () => {
          console.warn("WebSocket error, falling back to polling");
          startFallbackPolling(validationId);
        };

        ws.onclose = () => {
          if (status !== "completed" && status !== "failed") {
            startFallbackPolling(validationId);
          }
        };
      } catch (err) {
        startFallbackPolling(validationId);
      }
    },
    [disconnect, startFallbackPolling, status]
  );

  useEffect(() => () => disconnect(), [disconnect]);

  return { sections, rawReport, status, connect, disconnect };
}
