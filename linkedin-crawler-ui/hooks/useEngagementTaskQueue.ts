"use client";

import { useCallback, useRef, useState } from "react";

export type EngagementQueueTask<T = void> = {
  label?: string;
  run: () => Promise<T>;
  onSuccess?: (result: T) => void;
  onFailure?: (error: Error) => void;
};

/**
 * Hàng đợi FIFO — gắn với session modal (parent), không hủy khi đóng detail.
 * Gọi ``cancelPending()`` chỉ khi đóng hẳn modal phiên.
 */
export function useEngagementTaskQueue() {
  const queueRef = useRef<EngagementQueueTask<unknown>[]>([]);
  const processingRef = useRef(false);
  const [pendingCount, setPendingCount] = useState(0);

  const updatePendingCount = useCallback(() => {
    const queued = queueRef.current.length;
    const running = processingRef.current ? 1 : 0;
    setPendingCount(queued + running);
  }, []);

  const processQueue = useCallback(async () => {
    if (processingRef.current) return;
    processingRef.current = true;
    updatePendingCount();

    try {
      while (queueRef.current.length > 0) {
        const task = queueRef.current.shift() as EngagementQueueTask<unknown>;
        updatePendingCount();
        try {
          const result = await task.run();
          task.onSuccess?.(result);
        } catch (error) {
          const err =
            error instanceof Error ? error : new Error(String(error));
          task.onFailure?.(err);
        }
      }
    } finally {
      processingRef.current = false;
      updatePendingCount();
      if (queueRef.current.length > 0) {
        void processQueue();
      }
    }
  }, [updatePendingCount]);

  const enqueue = useCallback(
    <T,>(task: EngagementQueueTask<T>) => {
      queueRef.current.push(task as EngagementQueueTask<unknown>);
      updatePendingCount();
      void processQueue();
    },
    [processQueue, updatePendingCount],
  );

  /** Chỉ xóa tác vụ chưa chạy (đóng modal phiên). Tác vụ đang chạy vẫn hoàn tất. */
  const cancelPending = useCallback(() => {
    queueRef.current = [];
    updatePendingCount();
  }, [updatePendingCount]);

  return {
    enqueue,
    cancelPending,
    pendingCount,
    isProcessing: pendingCount > 0,
  };
}
