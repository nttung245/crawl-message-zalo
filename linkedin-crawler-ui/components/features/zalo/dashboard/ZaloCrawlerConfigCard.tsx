"use client";

import { useState } from "react";

import { MaterialIcon } from "@/components/ui";
import type { ZaloCrawlerFlowValue } from "@/hooks/useZaloCrawlerFlow";

import { ZaloGroupInputList } from "./ZaloGroupInputList";

interface ZaloCrawlerConfigCardProps {
  flow: ZaloCrawlerFlowValue;
}

const AUTH_LABELS = {
  confirmed: "Đã đăng nhập",
  waiting_scan: "Đang thao tác trên Zalo",
  qr_expired: "Phiên QR hết hạn",
  not_logged_in: "Chưa đăng nhập",
  checking: "Đang kiểm tra",
} as const;

function authStateTone(status: ZaloCrawlerFlowValue["authStatus"]): string {
  switch (status) {
    case "confirmed":
      return "border-secondary-container bg-secondary-container/20 text-on-secondary-container";
    case "waiting_scan":
      return "border-primary/20 bg-primary/10 text-primary";
    case "qr_expired":
      return "border-error-container bg-error-container/40 text-error";
    case "not_logged_in":
      return "border-outline-variant bg-surface text-on-surface-variant";
    default:
      return "border-outline-variant bg-surface text-on-surface-variant";
  }
}

function authStateLabel(status: ZaloCrawlerFlowValue["authStatus"]): string {
  return AUTH_LABELS[status] ?? AUTH_LABELS.checking;
}

export function ZaloCrawlerConfigCard({ flow }: ZaloCrawlerConfigCardProps) {
  const [isCrawledOpen, setIsCrawledOpen] = useState(false);

  return (
    <section className="flex flex-col gap-md">
      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="border-surface-variant mb-md flex items-center gap-2 border-b pb-md">
          <MaterialIcon name="settings_input_component" className="text-primary" />
          <h2 className="text-h3 font-semibold">{"Thiết lập crawl Zalo"}</h2>
        </div>

        <div className={`mb-md rounded-xl border px-md py-sm ${authStateTone(flow.authStatus)}`}>
          <div className="flex items-center justify-between gap-sm">
            <div>
              <div className="text-label-md mb-xs font-semibold uppercase">{"Trạng thái đăng nhập"}</div>
              <div className="text-body-md font-semibold">
                {flow.isCheckingLoginStatus ? AUTH_LABELS.checking : authStateLabel(flow.authStatus)}
              </div>
            </div>
          </div>
        </div>

        <div className="mb-md flex flex-wrap gap-sm">
          {flow.manualViewerUrl ? (
            <button
              type="button"
              className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void flow.startSession()}
              disabled={
                flow.isCheckingLoginStatus ||
                flow.isSubmittingGroups ||
                flow.isResumingSession ||
                flow.isEndingSession
              }
            >
              {"Mở Zalo"}
            </button>
          ) : null}

          {(flow.hasConfirmedSession || flow.authStatus === "not_logged_in") ? (
            <button
              type="button"
              className="bg-primary text-on-primary hover:bg-primary-container rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() =>
                void (flow.hasConfirmedSession
                  ? flow.startCrawlForGroups()
                  : flow.openManualScreen())
              }
              disabled={
                flow.isCheckingLoginStatus ||
                flow.isSubmittingGroups ||
                flow.isResumingSession ||
                flow.isEndingSession
              }
            >
              {flow.isEndingSession
                ? "Đang kết thúc phiên..."
                : flow.isSubmittingGroups
                  ? "Đang tạo job..."
                  : flow.isResumingSession
                    ? "Đang kiểm tra lại..."
                    : flow.hasConfirmedSession
                      ? "Chạy Crawl"
                      : "Mở Zalo & đăng nhập"}
            </button>
          ) : null}

          <button
            type="button"
            className="rounded-lg border border-red-300 bg-red-50 px-lg py-sm text-sm font-bold uppercase text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void flow.endSession()}
            disabled={!flow.sessionId || flow.isEndingSession || flow.isSubmittingGroups}
          >
            {flow.isEndingSession ? "Đang kết thúc phiên..." : "Kết thúc phiên"}
          </button>
        </div>

        <div className="mb-md rounded-xl border border-outline-variant bg-surface p-md">
          <h3 className="text-body-md font-semibold text-on-surface">{"Hướng dẫn sử dụng Zalo Crawler"}</h3>
          <div className="mt-sm space-y-1 text-body-sm text-on-surface">
            <p>{"Bước 1: Nhấn nút “Mở Zalo” để khởi động phiên đăng nhập. Nhấn Connect ở trang noVNC."}</p>
            <p>{"Bước 2: Tiến hành đăng nhập tài khoản Zalo bằng cách quét QR."}</p>
            <p>
              {
                "Bước 3: Sau khi đăng nhập thành công, quay lại hệ thống và nhập tên nhóm muốn crawl, hoặc chọn một nhóm đã được lưu trước đó."
              }
            </p>
            <p>{"Bước 4: Nhấn “Chạy Crawl” để bắt đầu quá trình thu thập dữ liệu."}</p>
          </div>
          <div className="mt-sm rounded-lg border border-amber-300 bg-amber-50 px-sm py-xs text-body-sm text-amber-900">
            {
              "⚠️ Lưu ý: Để quá trình crawl diễn ra ổn định và tránh lỗi, vui lòng hạn chế thao tác hoặc tương tác với giao diện Zalo trong khi hệ thống đang chạy crawl."
            }
          </div>
        </div>

        <div className="border-outline-variant bg-surface-container-low mb-md rounded-xl border p-md">
          <div className="flex flex-wrap items-center justify-between gap-sm">
            <div>
              <div className="text-label-md text-on-surface-variant font-semibold uppercase">{"Nhóm đã crawl"}</div>
              <div className="text-body-sm text-on-surface-variant">{"Tổng nhóm: "} {flow.crawledGroupsTotal}</div>
            </div>
            <div className="flex flex-wrap items-center gap-sm">
              {flow.crawledGroupsSheetUrl ? (
                <a
                  href={flow.crawledGroupsSheetUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary inline-flex items-center gap-1 text-sm font-semibold hover:underline"
                >
                  <MaterialIcon name="open_in_new" className="text-base" />
                  {"Mở Google Sheets"}
                </a>
              ) : null}
              <button
                type="button"
                className="border-outline-variant bg-surface hover:bg-surface-container-high inline-flex items-center gap-1 rounded-lg border px-md py-xs text-xs font-bold uppercase"
                onClick={() => setIsCrawledOpen((previous) => !previous)}
              >
                {isCrawledOpen ? "Thu gọn" : "Xem danh sách"}
              </button>
            </div>
          </div>

          {isCrawledOpen ? (
            <div className="mt-sm max-h-72 overflow-y-auto pr-1">
              {flow.isLoadingCrawledGroups ? (
                <div className="text-body-sm text-on-surface-variant">{"Đang tải danh sách nhóm đã crawl..."}</div>
              ) : flow.crawledGroupsError ? (
                <div className="border-error-container bg-error-container/40 text-error rounded-lg border px-md py-sm text-body-sm">
                  {flow.crawledGroupsError}
                </div>
              ) : flow.crawledGroups.length === 0 ? (
                <div className="text-body-sm text-on-surface-variant">{"Chưa có nhóm nào được crawl trước đó."}</div>
              ) : (
                <div className="grid gap-sm sm:grid-cols-2">
                  {flow.crawledGroups.map((group) => (
                    <button
                      key={`${group.group_name}-${group.sheet_tab}`}
                      type="button"
                      className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-md py-sm text-left transition"
                      onClick={() => flow.addCrawledGroup(group)}
                    >
                      <div className="text-body-sm text-on-surface font-semibold">{group.group_name}</div>
                      <div className="text-body-sm text-on-surface-variant">Tab: {group.sheet_tab}</div>
                      <div className="text-body-sm text-on-surface-variant">{"Tin nhắn: "} {group.message_count}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : null}
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
      </div>
    </section>
  );
}
