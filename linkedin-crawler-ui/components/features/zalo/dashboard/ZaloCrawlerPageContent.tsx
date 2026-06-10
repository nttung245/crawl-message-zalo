"use client";

import { useState } from "react";
import { useZaloCrawlerFlow } from "@/hooks/useZaloCrawlerFlow";

import { ZaloDashboardView } from "./ZaloDashboardView";
import { ZaloChatView } from "./ZaloChatView";
import { ZaloAgentTestPanel } from "./ZaloAgentTestPanel";

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
  const [activeTab, setActiveTab] = useState<"dashboard" | "agent">("dashboard");

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

      <div className="border-outline-variant bg-surface-container-lowest flex flex-wrap gap-sm rounded-2xl border p-sm">
        {([
          ["dashboard", "Dashboard"],
          ["agent", "Agent Test"],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setActiveTab(value)}
            className={`rounded-xl px-md py-sm text-body-sm font-semibold transition ${
              activeTab === value ? "bg-primary text-on-primary" : "text-on-surface hover:bg-surface-container-high"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {activeTab === "agent" ? (
        <ZaloAgentTestPanel userId={flow.userId} />
      ) : isInChatView ? (
        <ZaloChatView flow={flow} onBackToDashboard={handleBackToDashboard} />
      ) : (
        <ZaloDashboardView flow={flow} onEnterChat={handleEnterChat} />
      )}
    </div>
  );
}
