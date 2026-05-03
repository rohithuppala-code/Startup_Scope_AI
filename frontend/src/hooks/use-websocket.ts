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
      setRawReport(null);
      setStatus("connecting");
      validationIdRef.current = validationId;
      attemptRef.current = 0;

      // Poll the public status endpoint every 2s.
      // Falls back to the authed endpoint if status endpoint is unavailable.
      intervalRef.current = setInterval(async () => {
        const vid = validationIdRef.current;
        if (!vid) return;

        attemptRef.current += 1;

        // Timeout after 5 minutes (150 × 2s)
        if (attemptRef.current > 150) {
          setStatus("failed");
          disconnect();
          return;
        }

        try {
          // Use the public /status endpoint (no auth needed)
          const userId = useUserStore.getState().userId;
          const fallbackHeaders: Record<string, string> = {};
          if (userId) fallbackHeaders["x-user-id"] = userId;
          const res = await fetch(`${API_BASE}/api/v1/validate/${vid}/status`).catch(
            () => fetch(`${API_BASE}/api/v1/validate/${vid}`, { headers: fallbackHeaders })
          );
          if (!res.ok) return; // keep polling on transient errors

          const data = (await res.json()) as {
            status: string;
            report_json?: Record<string, unknown>;
          };

          if (data.status === "completed") {
            setStatus("completed");
            if (data.report_json && typeof data.report_json === "object") {
              // Expose both: (1) raw object for LiveIdeaCard feasibility/tabs
              //              (2) flattened sections for StudioPage report rendering
              setRawReport(data.report_json);
              setSections(flattenReportJson(data.report_json));
            }
            disconnect();
          } else if (data.status === "failed") {
            setStatus("failed");
            disconnect();
          } else {
            // pending / processing → show streaming spinner
            setStatus("streaming");
          }
        } catch {
          // Network blip — keep polling silently
        }
      }, 2000);
    },
    [disconnect]
  );

  // Cleanup on unmount
  useEffect(() => () => disconnect(), [disconnect]);

  return { sections, rawReport, status, connect, disconnect };
}
