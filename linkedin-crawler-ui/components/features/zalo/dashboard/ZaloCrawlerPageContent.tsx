"use client";

import { useZaloCrawlerFlow } from "@/hooks/useZaloCrawlerFlow";

import { ZaloCrawlProgressPanel } from "./ZaloCrawlProgressPanel";
import { ZaloCrawlResultSection } from "./ZaloCrawlResultSection";
import { ZaloCrawlerConfigCard } from "./ZaloCrawlerConfigCard";

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

  return (
    <div className="flex flex-col gap-xl">
      <div>
        <h1 className="text-h1 text-on-surface mb-xs font-semibold">
          Zalo Group Crawler
        </h1>
        <p className="text-body-lg text-on-surface-variant">
          {"Manual mode qua noVNC: login tr\u01b0\u1edbc, crawl sau."}
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

      <div className="grid gap-lg xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <ZaloCrawlerConfigCard flow={flow} />
        <ZaloCrawlProgressPanel
          jobs={flow.jobs}
          summary={flow.summary}
          onRetryGroup={flow.retryGroup}
        />
      </div>

      <ZaloCrawlResultSection jobs={flow.jobs} />
    </div>
  );
}
