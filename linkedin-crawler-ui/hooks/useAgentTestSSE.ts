"use client";

import { useCallback, useRef, useState } from "react";

import { API_BASE_URL, API_KEY } from "@/lib/env";
import type {
  AgentTestExtractRequest,
  AgentTestExtractResult,
  AgentTestProgress,
} from "@/types/zalo-api";

export interface UseAgentTestSSEReturn {
  results: AgentTestExtractResult[] | null;
  progress: AgentTestProgress | null;
  summary: { total: number; extracted: number; not_listing: number; failed: number } | null;
  isStreaming: boolean;
  error: string | null;
  startStream: (request: AgentTestExtractRequest) => void;
  reset: () => void;
  timedOut: boolean;
}

const DEFAULT_TIMEOUT_MS = Number(
  process.env.NEXT_PUBLIC_AGENT_TEST_TIMEOUT_MS ?? "120000",
);

export function useAgentTestSSE(timeoutMs = DEFAULT_TIMEOUT_MS): UseAgentTestSSEReturn {
  const [results, setResults] = useState<AgentTestExtractResult[] | null>(null);
  const [progress, setProgress] = useState<AgentTestProgress | null>(null);
  const [summary, setSummary] = useState<UseAgentTestSSEReturn["summary"]>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const cancelledRef = useRef(false);
  const timedOutRef = useRef(false);

  const startStream = useCallback(
    (request: AgentTestExtractRequest) => {
      setResults(null);
      setProgress(null);
      setSummary(null);
      setError(null);
      setTimedOut(false);
      setIsStreaming(true);

      cancelledRef.current = false;
      timedOutRef.current = false;

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const signal = controller.signal;

      const timer = setTimeout(() => {
        if (!cancelledRef.current) {
          cancelledRef.current = true;
          timedOutRef.current = true;
          controller.abort();
          setTimedOut(true);
        }
      }, timeoutMs);

      const run = async () => {
        try {
          const response = await fetch(
            `${API_BASE_URL}/api/apartment-agent/test-extract`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "x-api-key": API_KEY,
                Accept: "text/event-stream",
              },
              body: JSON.stringify({ ...request, stream: true }),
              signal,
            },
          );

          if (!response.ok) {
            const text = await response.text().catch(() => "");
            throw new Error(text || `HTTP ${response.status}`);
          }

          const reader = response.body?.getReader();
          if (!reader) throw new Error("No response body");

          const decoder = new TextDecoder();
          let buffer = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (line.startsWith("event: complete")) {
                break;
              }
              if (!line.startsWith("data: ")) continue;

              let data: Record<string, unknown>;
              try {
                data = JSON.parse(line.slice(6));
              } catch {
                continue;
              }

              if (data.type === "progress") {
                setProgress({
                  completed: data.completed as number,
                  total: data.total as number,
                  extracted: data.extracted as number,
                  not_listing: data.not_listing as number,
                  failed: data.failed as number,
                });
              } else if (data.type === "result") {
                setResults(data.results as AgentTestExtractResult[]);
                setSummary({
                  total: data.total as number,
                  extracted: data.extracted as number,
                  not_listing: data.not_listing as number,
                  failed: data.failed as number,
                });
                setProgress(null);
              } else if (data.type === "error") {
                throw new Error((data.message as string) || "SSE error");
              }
            }
          }
        } catch (err: unknown) {
          if (cancelledRef.current) return;
          if (err instanceof DOMException && err.name === "AbortError") {
            if (!timedOutRef.current) {
              setError("Yêu cầu đã bị hủy");
            }
            return;
          }
          setError(err instanceof Error ? err.message : "Lỗi không xác định");
        } finally {
          if (!cancelledRef.current) {
            cancelledRef.current = true;
            clearTimeout(timer);
            setIsStreaming(false);
          }
        }
      };

      run();
    },
    [timeoutMs],
  );

  const reset = useCallback(() => {
    cancelledRef.current = true;
    timedOutRef.current = false;
    abortRef.current?.abort();
    setResults(null);
    setProgress(null);
    setSummary(null);
    setError(null);
    setTimedOut(false);
    setIsStreaming(false);
  }, []);

  return { results, progress, summary, isStreaming, error, startStream, reset, timedOut };
}
