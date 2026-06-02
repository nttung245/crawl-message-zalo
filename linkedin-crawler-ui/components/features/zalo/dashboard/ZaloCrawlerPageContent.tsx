"use client";

import { useMemo, useState } from "react";

import { useZaloCrawlerFlow } from "@/hooks/useZaloCrawlerFlow";
import type { ZaloLibraryMessage } from "@/types/zalo-api";

import { ZaloBroadcastPanel } from "./ZaloBroadcastPanel";
import { ZaloCrawlProgressPanel } from "./ZaloCrawlProgressPanel";
import { ZaloCrawlResultSection } from "./ZaloCrawlResultSection";
import { ZaloCrawlerConfigCard } from "./ZaloCrawlerConfigCard";
import { ZaloSupabaseLibraryPanel } from "./ZaloSupabaseLibraryPanel";

function InlineBanner({
  tone,
  message,
}: {
  tone: "success" | "error" | "warning";
  message: string;
}) {
  const toneClasses =
    tone === "success"
      ? "border-secondary-container bg-secondary-container/20 text-on-secondary-container"
      : tone === "error"
        ? "border-error-container bg-error-container/40 text-error"
        : "border-outline-variant bg-surface-container-low text-on-surface";

  return (
    <div className={`rounded-xl border px-md py-sm text-body-sm ${toneClasses}`}>
      {message}
    </div>
  );
}

export function ZaloCrawlerPageContent() {
  const flow = useZaloCrawlerFlow();
  const [activeTab, setActiveTab] = useState<"crawl" | "library" | "broadcast">("crawl");
  const [libraryMessages, setLibraryMessages] = useState<ZaloLibraryMessage[]>([]);
  const [selectedMessageIds, setSelectedMessageIds] = useState<string[]>([]);
  const selectedMessages = useMemo(
    () => libraryMessages.filter((message) => selectedMessageIds.includes(message.id)),
    [libraryMessages, selectedMessageIds],
  );

  return (
    <div className="flex flex-col gap-xl">
      <div>
        <h1 className="mb-xs text-h1 font-semibold text-on-surface">Zalo Crawler</h1>
        <p className="text-body-lg text-on-surface-variant">
          Crawl tin nhắn và hình ảnh trong group Zalo, lưu vào Supabase rồi dùng lại cho thư viện nội dung hoặc chiến dịch gửi.
        </p>
      </div>

      {flow.feedbackMessage ? (
        <InlineBanner tone="success" message={flow.feedbackMessage} />
      ) : null}
      {flow.warningMessage ? (
        <InlineBanner tone="warning" message={flow.warningMessage} />
      ) : null}
      {flow.errorMessage ? (
        <InlineBanner tone="error" message={flow.errorMessage} />
      ) : null}

      <div className="border-outline-variant bg-surface-container-lowest flex flex-wrap gap-sm rounded-2xl border p-sm">
        {[
          ["crawl", "Crawl"],
          ["library", "Thư viện tin"],
          ["broadcast", "Chiến dịch gửi"],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setActiveTab(value as "crawl" | "library" | "broadcast")}
            className={`rounded-xl px-md py-sm text-body-sm font-semibold transition ${
              activeTab === value ? "bg-primary text-on-primary" : "text-on-surface hover:bg-surface-container-high"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === "crawl" ? (
        <>
          <div className="grid gap-lg xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
            <ZaloCrawlerConfigCard flow={flow} />
            <ZaloCrawlProgressPanel
              jobs={flow.jobs}
              summary={flow.summary}
              onRetryGroup={flow.retryGroup}
            />
          </div>

          <ZaloCrawlResultSection jobs={flow.jobs} />
        </>
      ) : null}

      {activeTab === "library" ? (
        <ZaloSupabaseLibraryPanel
          userId={flow.userId}
          selectedMessageIds={selectedMessageIds}
          onSelectedMessageIdsChange={setSelectedMessageIds}
          onMessagesLoaded={setLibraryMessages}
        />
      ) : null}

      {activeTab === "broadcast" ? (
        <ZaloBroadcastPanel
          userId={flow.userId}
          selectedMessageIds={selectedMessageIds}
          selectedMessages={selectedMessages}
        />
      ) : null}
    </div>
  );
}
