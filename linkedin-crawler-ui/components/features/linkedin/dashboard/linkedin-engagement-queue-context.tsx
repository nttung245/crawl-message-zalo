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
import { SessionPostDetailModal } from "@/components/features/linkedin/dashboard/LinkedIn-SessionPostDetailModal";
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
    post?: Record<string, unknown> | null,
    rowNumber?: number | null,
    session?: any | null,
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
  const { refreshDashboardData, updatePostInSessions, email } = useDashboard();
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
    post?: Record<string, unknown> | null;
    rowNumber?: number | null;
    session?: any | null;
  } | null>(null);

  const [errorDetailPost, setErrorDetailPost] = useState<{
    post: Record<string, unknown>;
    rowNumber: number;
    session: any;
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
    (
      kind: EngagementFeedbackKind,
      message: string,
      post?: Record<string, unknown> | null,
      rowNumber?: number | null,
      session?: any | null,
    ) => {
      setEngagementError({ kind, message, post, rowNumber, session });
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
        onViewPostDetails={(post, rowNumber, session) => {
          setErrorDetailPost({ post, rowNumber, session });
        }}
        zIndexClass="z-[100]"
      />
      {pendingCount > 0 ? (
        <EngagementQueueGlobalBadge count={pendingCount} />
      ) : null}

      {errorDetailPost ? (
        <SessionPostDetailModal
          session={errorDetailPost.session}
          post={errorDetailPost.post}
          rowNumber={errorDetailPost.rowNumber}
          dashboardEmail={email}
          onRefreshSessions={refreshDashboardData}
          onReactionSucceeded={(rowNum, patch, postUrlForSync) => {
            if (updatePostInSessions) {
              updatePostInSessions(
                errorDetailPost.session.id_session_crawl,
                rowNum,
                patch,
                postUrlForSync,
              );
            }
            setErrorDetailPost((prev) =>
              prev ? { ...prev, post: { ...prev.post, ...patch } } : null,
            );
          }}
          onClose={() => setErrorDetailPost(null)}
        />
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
