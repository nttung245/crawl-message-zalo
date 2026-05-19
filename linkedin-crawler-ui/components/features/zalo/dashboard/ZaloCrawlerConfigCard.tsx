"use client";

import type { ZaloCrawlerFlowValue } from "@/hooks/useZaloCrawlerFlow";
import { MaterialIcon } from "@/components/ui";

import { ZaloGroupInputList } from "./ZaloGroupInputList";

interface ZaloCrawlerConfigCardProps {
  flow: ZaloCrawlerFlowValue;
}

function authStateTone(status: ZaloCrawlerFlowValue["authStatus"]): string {
  switch (status) {
    case "confirmed":
      return "border-secondary-container bg-secondary-container/20 text-on-secondary-container";
    case "qr_expired":
      return "border-error-container bg-error-container/40 text-error";
    case "waiting_scan":
      return "border-primary/20 bg-primary/10 text-primary";
    default:
      return "border-outline-variant bg-surface text-on-surface-variant";
  }
}

function authStateLabel(status: ZaloCrawlerFlowValue["authStatus"]): string {
  switch (status) {
    case "confirmed":
      return "Phiên Zalo đã xác nhận";
    case "qr_expired":
      return "QR đã hết hạn";
    case "waiting_scan":
      return "Đang chờ quét QR";
    default:
      return "Chưa khởi tạo phiên";
  }
}

export function ZaloCrawlerConfigCard({
  flow,
}: ZaloCrawlerConfigCardProps) {
  return (
    <section className="flex flex-col gap-md">
      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="border-surface-variant mb-md flex items-center gap-2 border-b pb-md">
          <MaterialIcon name="settings_input_component" className="text-primary" />
          <h2 className="text-h3 font-semibold">Thiết lập crawl Zalo</h2>
        </div>

        <div className={`mb-md rounded-xl border px-md py-sm ${authStateTone(flow.authStatus)}`}>
          <div className="flex flex-wrap items-center justify-between gap-sm">
            <div>
              <div className="text-label-md mb-xs font-semibold uppercase">
                Trạng thái phiên
              </div>
              <div className="text-body-md font-semibold">
                {authStateLabel(flow.authStatus)}
              </div>
            </div>
            {flow.sessionId ? (
              <div className="text-body-sm break-all opacity-80">
                Session: {flow.sessionId}
              </div>
            ) : null}
          </div>
        </div>

        <div className="mb-md flex flex-wrap gap-sm">
          <button
            type="button"
            className="bg-primary text-on-primary hover:bg-primary-container rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() =>
              void (flow.hasConfirmedSession ? flow.startCrawlForGroups() : flow.startSession())
            }
            disabled={flow.isInitializingSession || flow.isSubmittingGroups}
          >
            {flow.hasConfirmedSession
              ? flow.isSubmittingGroups
                ? "Đang tạo job..."
                : "Chạy Crawl"
              : flow.isInitializingSession
                ? "Đang tạo QR..."
                : "Start Crawl"}
          </button>

          <button
            type="button"
            className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void flow.refreshQrCode()}
            disabled={!flow.sessionId || flow.hasConfirmedSession || flow.isRefreshingQr}
          >
            {flow.isRefreshingQr ? "Đang làm mới..." : "Làm mới QR"}
          </button>

          <button
            type="button"
            className="rounded-lg px-lg py-sm text-sm font-bold uppercase text-on-surface-variant disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void flow.endSession()}
            disabled={!flow.sessionId}
          >
            Kết thúc phiên
          </button>
        </div>

        <div className="mb-md grid gap-sm sm:grid-cols-3">
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              Bước 1
            </div>
            <div className="text-body-sm text-on-surface">
              Tạo phiên và quét QR bằng Zalo.
            </div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              Bước 2
            </div>
            <div className="text-body-sm text-on-surface">
              Thêm nhiều tên nhóm và tab Sheets nếu cần.
            </div>
          </div>
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
              Bước 3
            </div>
            <div className="text-body-sm text-on-surface">
              Theo dõi tiến độ realtime, trạng thái từng nhóm và kết quả ghi Sheets.
            </div>
          </div>
        </div>

        <div className={!flow.hasConfirmedSession ? "opacity-70" : undefined}>
          <ZaloGroupInputList
            rows={flow.groupRows}
            disabled={!flow.hasConfirmedSession || flow.isSubmittingGroups}
            onAddRow={flow.addGroupRow}
            onUpdateRow={flow.updateGroupRow}
            onRemoveRow={flow.removeGroupRow}
          />
        </div>

        {!flow.hasConfirmedSession ? (
          <div className="border-outline-variant bg-surface-container-low mt-md rounded-xl border px-md py-sm text-body-sm text-on-surface-variant">
            Hoàn tất đăng nhập QR trước khi nhập nhóm và chạy crawl.
          </div>
        ) : null}
      </div>
    </section>
  );
}
