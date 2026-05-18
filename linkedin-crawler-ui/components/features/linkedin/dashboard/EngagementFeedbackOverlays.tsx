"use client";

import { MaterialIcon } from "@/components/ui";
import {
  ENGAGEMENT_ERROR_TITLE,
  ENGAGEMENT_ROLLBACK_NOTE,
  ENGAGEMENT_SUCCESS_COPY,
  engagementSuccessIcon,
  type EngagementFeedbackKind,
} from "@/lib/linkedin-engagement-feedback";

export interface EngagementFeedbackOverlaysProps {
  successKind: EngagementFeedbackKind | null;
  successClosing?: boolean;
  onSuccessClose: () => void;
  onSuccessOk: () => void;
  error: { kind: EngagementFeedbackKind; message: string } | null;
  onErrorDismiss: () => void;
  zIndexClass?: string;
}

export function EngagementFeedbackOverlays({
  successKind,
  successClosing = false,
  onSuccessClose,
  onSuccessOk,
  error,
  onErrorDismiss,
  zIndexClass = "z-[80]",
}: EngagementFeedbackOverlaysProps) {
  return (
    <>
      {successKind ? (
        <div
          className={`fixed inset-0 ${zIndexClass} flex items-end justify-center p-md sm:items-center`}
          role="presentation"
        >
          <button
            type="button"
            className={`absolute inset-0 bg-black/55 backdrop-blur-md ${
              successClosing
                ? "rx-webhook-overlay--out"
                : "rx-webhook-overlay--in"
            }`}
            aria-label="Đóng thông báo"
            onClick={onSuccessClose}
          />
          <div
            className={`border-outline-variant/70 bg-surface-container-lowest relative z-10 w-[min(92vw,500px)] overflow-hidden rounded-2xl border shadow-[0_24px_60px_rgb(0_0_0_/_.18)] ring-1 ring-primary/10 ${
              successClosing
                ? "rx-webhook-dialog--out"
                : "rx-webhook-dialog--in"
            }`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="engagement-success-title"
          >
            <div className="from-primary/20 via-primary/5 h-1 bg-gradient-to-r to-transparent" />
            <div className="p-lg sm:p-xl">
              <div className="flex items-start gap-md">
                <span className="bg-primary/10 text-primary inline-flex size-11 shrink-0 items-center justify-center rounded-full">
                  <MaterialIcon
                    name={engagementSuccessIcon(successKind)}
                    className="text-[24px]"
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <span className="bg-primary/10 text-primary inline-flex rounded-full px-sm py-0.5 text-[10px] font-bold tracking-[0.12em] uppercase">
                    Thành công
                  </span>
                  <h3
                    id="engagement-success-title"
                    className="text-h2 text-on-surface mt-2 font-semibold tracking-tight"
                  >
                    {ENGAGEMENT_SUCCESS_COPY[successKind].title}
                  </h3>
                  <p className="text-body-md text-on-surface-variant mt-sm leading-relaxed whitespace-pre-line">
                    {ENGAGEMENT_SUCCESS_COPY[successKind].body}
                  </p>
                </div>
              </div>
              <div className="mt-lg flex flex-col-reverse gap-sm sm:flex-row sm:justify-end">
                <button
                  type="button"
                  className="border-outline-variant text-on-surface hover:bg-surface-container-high rounded-xl border px-lg py-sm text-sm font-bold uppercase transition-colors"
                  onClick={onSuccessClose}
                >
                  Đóng
                </button>
                <button
                  type="button"
                  className="bg-primary text-on-primary hover:bg-primary-container min-w-28 rounded-xl px-lg py-sm text-sm font-bold uppercase shadow-[0_10px_24px_rgb(0_93_143_/_.22)] transition-[transform,background-color,box-shadow] duration-200 ease-out hover:shadow-[0_12px_28px_rgb(0_93_143_/_.28)] active:scale-[0.98]"
                  onClick={onSuccessOk}
                >
                  OK
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {error ? (
        <div
          className={`fixed inset-0 ${zIndexClass} flex items-end justify-center p-md sm:items-center`}
          role="presentation"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/55 backdrop-blur-md"
            aria-label="Đóng thông báo lỗi"
            onClick={onErrorDismiss}
          />
          <div
            className="border-error-container/70 bg-surface-container-lowest relative z-10 w-[min(92vw,500px)] overflow-hidden rounded-2xl border shadow-[0_24px_60px_rgb(0_0_0_/_.18)] ring-1 ring-error/20"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="engagement-error-title"
          >
            <div className="from-error/25 via-error/5 h-1 bg-gradient-to-r to-transparent" />
            <div className="p-lg sm:p-xl">
              <div className="flex items-start gap-md">
                <span className="bg-error/10 text-error inline-flex size-11 shrink-0 items-center justify-center rounded-full">
                  <MaterialIcon name="error" className="text-[24px]" />
                </span>
                <div className="min-w-0 flex-1">
                  <span className="bg-error/10 text-error inline-flex rounded-full px-sm py-0.5 text-[10px] font-bold tracking-[0.12em] uppercase">
                    Playwright
                  </span>
                  <h3
                    id="engagement-error-title"
                    className="text-h2 text-on-surface mt-2 font-semibold tracking-tight"
                  >
                    {ENGAGEMENT_ERROR_TITLE[error.kind]}
                  </h3>
                  <p className="text-body-md text-on-surface mt-sm leading-relaxed whitespace-pre-wrap">
                    {error.message}
                  </p>
                  <p className="text-body-sm text-on-surface-variant mt-md leading-relaxed">
                    {ENGAGEMENT_ROLLBACK_NOTE}
                  </p>
                </div>
              </div>
              <div className="mt-lg flex justify-end">
                <button
                  type="button"
                  className="bg-error text-on-error min-w-28 rounded-xl px-lg py-sm text-sm font-bold uppercase"
                  onClick={onErrorDismiss}
                >
                  Đã hiểu
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
