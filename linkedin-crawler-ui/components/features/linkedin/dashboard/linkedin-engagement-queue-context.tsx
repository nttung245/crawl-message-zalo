"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useDashboard } from "@/components/features/dashboard/dashboard-context";
import { EngagementFeedbackOverlays } from "@/components/features/linkedin/dashboard/EngagementFeedbackOverlays";
import { MaterialIcon } from "@/components/ui";
import {
  useEngagementTaskQueue,
  type EngagementQueueTask,
} from "@/hooks/useEngagementTaskQueue";
import type { EngagementFeedbackKind } from "@/lib/linkedin-engagement-feedback";

export type LinkedInEngagementQueueValue = {
  enqueueEngagement: <T>(task: EngagementQueueTask<T>) => void;
  pendingCount: number;
  onEngagementSuccess: (kind: EngagementFeedbackKind) => void;
  enqueuePostEngagementSync: () => void;
  showEngagementFailure: (
    kind: EngagementFeedbackKind,
    message: string,
  ) => void;
  registerBackgroundSync: (runner: (() => Promise<void>) | null) => void;
};

const LinkedInEngagementQueueContext =
  createContext<LinkedInEngagementQueueValue | null>(null);

function EngagementQueueGlobalBadge({ count }: { count: number }) {
  return (
    <div
      className="border-outline-variant bg-surface-container-lowest text-on-surface fixed bottom-6 right-6 z-[90] flex items-center gap-2 rounded-full border px-md py-sm shadow-lg"
      role="status"
      aria-live="polite"
    >
      <MaterialIcon name="sync" className="text-primary text-[18px] animate-spin" />
      <span className="text-body-sm font-semibold">
        Nền: {count} tác vụ LinkedIn
      </span>
    </div>
  );
}

export function LinkedInEngagementQueueProvider({
  children,
}: {
  children: ReactNode;
}) {
  const { refreshDashboardData } = useDashboard();
  const { enqueue: enqueueEngagement, pendingCount } = useEngagementTaskQueue();

  const backgroundSyncRef = useRef<(() => Promise<void>) | null>(null);
  const engagementSuccessCloseTimerRef = useRef<number | null>(null);

  const [engagementSuccessKind, setEngagementSuccessKind] =
    useState<EngagementFeedbackKind | null>(null);
  const [engagementSuccessClosing, setEngagementSuccessClosing] =
    useState(false);
  const [engagementError, setEngagementError] = useState<{
    kind: EngagementFeedbackKind;
    message: string;
  } | null>(null);

  const registerBackgroundSync = useCallback(
    (runner: (() => Promise<void>) | null) => {
      backgroundSyncRef.current = runner;
    },
    [],
  );

  const scheduleEngagementSuccessClose = useCallback(() => {
    if (engagementSuccessCloseTimerRef.current !== null) return;
    setEngagementSuccessClosing(true);
    engagementSuccessCloseTimerRef.current = window.setTimeout(() => {
      engagementSuccessCloseTimerRef.current = null;
      setEngagementSuccessKind(null);
      setEngagementSuccessClosing(false);
    }, 180);
  }, []);

  useEffect(() => {
    return () => {
      if (engagementSuccessCloseTimerRef.current !== null) {
        window.clearTimeout(engagementSuccessCloseTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (engagementSuccessKind) setEngagementSuccessClosing(false);
  }, [engagementSuccessKind]);

  useEffect(() => {
    if (!engagementSuccessKind && !engagementError) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (engagementSuccessKind) {
        scheduleEngagementSuccessClose();
        return;
      }
      setEngagementError(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    engagementSuccessKind,
    engagementError,
    scheduleEngagementSuccessClose,
  ]);

  const onEngagementSuccess = useCallback((kind: EngagementFeedbackKind) => {
    setEngagementSuccessKind(kind);
    if (kind === "sync") {
      enqueueEngagement({
        label: "refresh_after_sync",
        run: () => refreshDashboardData(),
      });
    }
  }, [enqueueEngagement, refreshDashboardData]);

  /** Gọi sau khi Playwright thành công — đồng bộ sheet + refresh dashboard ở nền. */
  const enqueuePostEngagementSync = useCallback(() => {
    const runner = backgroundSyncRef.current;
    enqueueEngagement({
      label: "background_sync",
      run: async () => {
        if (runner) await runner();
        await refreshDashboardData();
      },
    });
  }, [enqueueEngagement, refreshDashboardData]);

  const showEngagementFailure = useCallback(
    (kind: EngagementFeedbackKind, message: string) => {
      setEngagementError({ kind, message });
    },
    [],
  );

  const handleEngagementOkConfirm = useCallback(() => {
    scheduleEngagementSuccessClose();
  }, [scheduleEngagementSuccessClose]);

  const value: LinkedInEngagementQueueValue = {
    enqueueEngagement,
    pendingCount,
    onEngagementSuccess,
    enqueuePostEngagementSync,
    showEngagementFailure,
    registerBackgroundSync,
  };

  return (
    <LinkedInEngagementQueueContext.Provider value={value}>
      {children}
      <EngagementFeedbackOverlays
        successKind={engagementSuccessKind}
        successClosing={engagementSuccessClosing}
        onSuccessClose={scheduleEngagementSuccessClose}
        onSuccessOk={handleEngagementOkConfirm}
        error={engagementError}
        onErrorDismiss={() => setEngagementError(null)}
        zIndexClass="z-[100]"
      />
      {pendingCount > 0 ? (
        <EngagementQueueGlobalBadge count={pendingCount} />
      ) : null}
    </LinkedInEngagementQueueContext.Provider>
  );
}

export function useLinkedInEngagementQueue(): LinkedInEngagementQueueValue {
  const ctx = useContext(LinkedInEngagementQueueContext);
  if (!ctx) {
    throw new Error(
      "useLinkedInEngagementQueue must be used within LinkedInEngagementQueueProvider",
    );
  }
  return ctx;
}

export function useLinkedInEngagementQueueOptional(): LinkedInEngagementQueueValue | null {
  return useContext(LinkedInEngagementQueueContext);
}
