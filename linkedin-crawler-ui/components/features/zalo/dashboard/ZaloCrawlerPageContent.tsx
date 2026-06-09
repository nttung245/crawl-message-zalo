"use client";

import { useState } from "react";
import { useZaloCrawlerFlow } from "@/hooks/useZaloCrawlerFlow";

import { ZaloDashboardView } from "./ZaloDashboardView";
import { ZaloChatView } from "./ZaloChatView";

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
  // Separate local view state from flow.userId to avoid routing conflicts
  const [activeAccountId, setActiveAccountId] = useState<string | null>(null);

  function handleEnterChat(accountId: string) {
    // Switch to the account context in the flow and then set local view
    if (accountId !== flow.userId) {
      flow.switchAccount(accountId);
    }
    setActiveAccountId(accountId);
  }

  function handleBackToDashboard() {
    setActiveAccountId(null);
  }

  const isInChatView = activeAccountId !== null;

  return (
    <div className="flex flex-col gap-md">
      {flow.feedbackMessage ? <InlineBanner tone="success" message={flow.feedbackMessage} /> : null}
      {flow.warningMessage ? <InlineBanner tone="warning" message={flow.warningMessage} /> : null}
      {flow.errorMessage ? <InlineBanner tone="error" message={flow.errorMessage} /> : null}

      {isInChatView ? (
        <ZaloChatView flow={flow} onBackToDashboard={handleBackToDashboard} />
      ) : (
        <ZaloDashboardView flow={flow} onEnterChat={handleEnterChat} />
      )}
    </div>
  );
}
