"use client";

import Image from "next/image";
import { useMemo, useState } from "react";

import { MaterialIcon } from "@/components/ui";
import type { ZaloCrawlerFlowValue } from "@/hooks/useZaloCrawlerFlow";

import { ZaloGroupInputList } from "./ZaloGroupInputList";
import { ZaloLiveGroupPicker } from "./ZaloLiveGroupPicker";

interface ZaloCrawlerConfigCardProps {
  flow: ZaloCrawlerFlowValue;
}

const AUTH_LABELS = {
  confirmed: "Đã đăng nhập",
  waiting_scan: "Đang chờ xác nhận",
  qr_expired: "QR đã hết hạn",
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

function StepBadge({
  index,
  active,
  done,
}: {
  index: number;
  active?: boolean;
  done?: boolean;
}) {
  const classes = done
    ? "bg-secondary-container text-on-secondary-container"
    : active
      ? "bg-primary text-on-primary"
      : "bg-surface-container-high text-on-surface-variant";

  return (
    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${classes}`}>
      {done ? <MaterialIcon name="check_circle" className="text-base" filled /> : index}
    </span>
  );
}

function BusyLabel({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="border-on-primary/40 border-t-on-primary h-4 w-4 animate-spin rounded-full border-2" />
      {text}
    </span>
  );
}

export function ZaloCrawlerConfigCard({ flow }: ZaloCrawlerConfigCardProps) {
  const [isCrawledOpen, setIsCrawledOpen] = useState(false);
  const selectedGroupCount = useMemo(
    () => flow.groupRows.filter((row) => row.groupName.trim()).length,
    [flow.groupRows],
  );
  const hasBlockingAction =
    flow.isStartingSession ||
    flow.isOpeningManualScreen ||
    flow.isSubmittingGroups ||
    flow.isVerifyingGroups ||
    flow.isResumingSession ||
    flow.isEndingSession;

  return (
    <section className="flex flex-col gap-md">
      <div className="border-outline-variant bg-surface-container-lowest rounded-xl border p-lg shadow-sm">
        <div className="border-surface-variant mb-md flex items-center gap-2 border-b pb-md">
          <MaterialIcon name="radar" className="text-primary" />
          <div>
            <h2 className="text-h3 font-semibold text-on-surface">Crawl tin nhắn Zalo</h2>
            <p className="text-body-sm text-on-surface-variant">
              Lấy tin nhắn và ảnh thật trong group đã chọn, lưu vào Supabase để xem lại hoặc dùng cho gửi hàng loạt.
            </p>
          </div>
        </div>

        <div className={`mb-md rounded-xl border px-md py-sm ${authStateTone(flow.authStatus)}`}>
          <div className="flex flex-wrap items-center justify-between gap-sm">
            <div>
              <div className="text-label-md mb-xs font-semibold uppercase">Trạng thái Zalo</div>
              <div className="text-body-md font-semibold">
                {flow.isCheckingLoginStatus ? AUTH_LABELS.checking : authStateLabel(flow.authStatus)}
              </div>
              <div className="text-body-sm mt-xs opacity-80">
                User phiên: <span className="font-mono">{flow.userId}</span>
              </div>
              <div className="text-body-sm mt-xs opacity-80">
                Worker hiện tại:{" "}
                {flow.isLoadingWorkers
                  ? "Đang kiểm tra"
                  : (() => {
                      const worker = flow.workers.find((item) => item.id === flow.selectedWorkerId);
                      if (!worker) return "Tự động";
                      return `${worker.label || worker.id} - ${worker.status ?? "unknown"}`;
                    })()}
              </div>
              {flow.workers.length > 0 ? (
              <div>
                <label
                  className="text-label-md font-semibold uppercase opacity-80"
                  htmlFor="zalo-worker-select"
                >
                  Account Zalo
                </label>
                <select
                  id="zalo-worker-select"
                  className="border-outline-variant bg-surface min-h-10 rounded-lg border px-sm py-xs text-body-sm font-semibold text-on-surface disabled:cursor-not-allowed disabled:opacity-60"
                  value={flow.selectedWorkerId}
                  onChange={(event) => flow.switchWorker(event.target.value)}
                  disabled={hasBlockingAction || flow.isSubmittingGroups || flow.isLoadingWorkers}
                >
                  {flow.workers.map((worker) => (
                    <option key={worker.id} value={worker.id}>
                      {worker.label || worker.id}
                    </option>
                  ))}
                </select>
                <span className="text-body-sm opacity-80">
                  {flow.isLoadingWorkers ? (
                    "Đang tải account..."
                  ) : (
                    (() => {
                      const worker = flow.workers.find((item) => item.id === flow.selectedWorkerId);
                      if (!worker) return "Tự động";
                      return `${worker.status ?? "unknown"} · ${worker.queue_state ?? "unknown"}`;
                    })()
                  )}
                </span>
              </div>
              ) : null}
              {flow.workersError ? (
                <div className="text-body-sm mt-xs text-error">{flow.workersError}</div>
              ) : null}
            </div>
            {flow.hasConfirmedSession ? (
              <div className="inline-flex items-center gap-1 rounded-full bg-secondary-container px-sm py-xs text-xs font-semibold text-on-secondary-container">
                <MaterialIcon name="verified_user" className="text-base" />
                Sẵn sàng crawl
              </div>
            ) : null}
          </div>
        </div>

        <div className="mb-md grid gap-sm lg:grid-cols-3">
          <div className="rounded-xl border border-outline-variant bg-surface p-md">
            <div className="mb-xs flex items-center gap-sm">
              <StepBadge index={1} active={!flow.hasConfirmedSession} done={flow.hasConfirmedSession} />
              <div className="font-semibold text-on-surface">Đăng nhập</div>
            </div>
            <p className="text-body-sm text-on-surface-variant">
              Quét QR hoặc mở màn hình Zalo khi tài khoản cần xác minh thêm.
            </p>
          </div>
          <div className="rounded-xl border border-outline-variant bg-surface p-md">
            <div className="mb-xs flex items-center gap-sm">
              <StepBadge index={2} active={flow.hasConfirmedSession && selectedGroupCount === 0} done={selectedGroupCount > 0} />
              <div className="font-semibold text-on-surface">Chọn group</div>
            </div>
            <p className="text-body-sm text-on-surface-variant">
              Tải danh sách group từ Zalo rồi tick nhóm cần crawl. Có thể nhập tay nếu cần.
            </p>
          </div>
          <div className="rounded-xl border border-outline-variant bg-surface p-md">
            <div className="mb-xs flex items-center gap-sm">
              <StepBadge index={3} active={flow.hasConfirmedSession && selectedGroupCount > 0} done={flow.summary.completed > 0} />
              <div className="font-semibold text-on-surface">Chạy crawl</div>
            </div>
            <p className="text-body-sm text-on-surface-variant">
              Hệ thống chạy tuần tự để ổn định. Khi đang crawl không thao tác vào cửa sổ Zalo.
            </p>
          </div>
        </div>

        <div className="mb-md flex flex-wrap gap-sm">
          {!flow.hasConfirmedSession ? (
            <button
              type="button"
              className="bg-primary text-on-primary hover:bg-primary-container inline-flex min-h-11 items-center justify-center rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void flow.startSession()}
            disabled={hasBlockingAction}
          >
              {flow.isStartingSession ? <BusyLabel text="Đang tạo QR" /> : "Hiện QR đăng nhập"}
            </button>
          ) : (
            <button
              type="button"
              className="bg-primary text-on-primary hover:bg-primary-container inline-flex min-h-11 items-center justify-center rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void flow.startCrawlForGroups()}
            disabled={!flow.canLaunchJobs}
          >
              {flow.isSubmittingGroups ? <BusyLabel text="Đang tạo job" /> : `Chạy crawl${selectedGroupCount > 0 ? ` ${selectedGroupCount} nhóm` : ""}`}
            </button>
          )}

          {flow.manualViewerUrl ? (
            <button
              type="button"
              className="border-outline-variant bg-surface hover:bg-surface-container-high inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
              onClick={() => void flow.openManualScreen()}
              disabled={hasBlockingAction}
            >
              <MaterialIcon name="open_in_new" className="text-base" />
              {flow.isOpeningManualScreen ? "Đang mở Zalo" : "Mở màn hình Zalo"}
            </button>
          ) : null}

          <button
            type="button"
            className="rounded-lg border border-red-300 bg-red-50 px-lg py-sm text-sm font-bold uppercase text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void flow.endSession()}
            disabled={!flow.sessionId || flow.isEndingSession || flow.isSubmittingGroups}
          >
            {flow.isEndingSession ? "Đang kết thúc phiên" : "Kết thúc phiên"}
          </button>

          <button
            type="button"
            className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void flow.restartSession()}
            disabled={hasBlockingAction || flow.isSubmittingGroups}
          >
            Đăng nhập lại
          </button>
        </div>

        {(flow.qrBase64 || flow.qrImageUrl) && !flow.hasConfirmedSession ? (
          <div className="border-outline-variant bg-surface mb-md rounded-xl border p-md">
            <div className="flex flex-col gap-md sm:flex-row sm:items-center">
              <Image
                src={flow.qrBase64 || flow.qrImageUrl || ""}
                alt="QR đăng nhập Zalo"
                width={256}
                height={256}
                unoptimized
                className="h-64 w-64 rounded-lg border border-outline-variant bg-white object-contain p-sm"
              />
              <div className="text-body-sm text-on-surface">
                <div className="text-body-md mb-xs font-semibold">Quét QR bằng ứng dụng Zalo</div>
                <p>Sau khi xác nhận trên điện thoại, trạng thái sẽ tự chuyển sang “Đã đăng nhập”.</p>
                {flow.manualViewerUrl ? (
                  <p className="mt-xs text-on-surface-variant">
                    Nếu Zalo yêu cầu xác minh thêm, bấm “Mở màn hình Zalo” để xử lý.
                  </p>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        <div className="mb-md rounded-xl border border-amber-300 bg-amber-50 px-md py-sm text-body-sm text-amber-900">
          <div className="flex gap-2">
            <MaterialIcon name="info" className="mt-0.5 text-base" />
            <div>
              Crawler chỉ lấy nội dung trong group được chọn: text và ảnh gửi trong tin nhắn. Ảnh đại diện, icon, sticker/reaction sẽ bị lọc bỏ.
            </div>
          </div>
        </div>

        <div className="border-outline-variant bg-surface mb-md rounded-xl border p-md">
          <div className="mb-sm flex flex-col gap-xs">
            <div className="text-label-md font-semibold uppercase text-on-surface-variant">
              Số tin crawl mỗi group
            </div>
            <div className="text-body-sm text-on-surface-variant">
              Hệ thống lấy từ tin mới nhất lên tin cũ và dừng khi đủ số lượng này.
            </div>
          </div>
          <div className="flex flex-col gap-sm sm:flex-row sm:items-center">
            <div className="flex flex-wrap gap-sm">
              {[20, 50, 100, 200].map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => flow.setMaxMessagesPerGroup(value)}
                  disabled={flow.isSubmittingGroups || flow.isVerifyingGroups}
                  className={`rounded-lg border px-md py-xs text-body-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60 ${
                    flow.maxMessagesPerGroup === value
                      ? "border-primary bg-primary text-on-primary"
                      : "border-outline-variant bg-surface hover:bg-surface-container-high"
                  }`}
                >
                  {value} tin
                </button>
              ))}
            </div>
            <label className="flex items-center gap-sm text-body-sm text-on-surface">
              <span>Tùy chỉnh</span>
              <input
                type="number"
                min={1}
                max={500}
                value={flow.maxMessagesPerGroup}
                onChange={(event) => {
                  const val = event.target.value;
                  if (val === "") return; // Allow empty while typing
                  const num = Number(val);
                  if (!Number.isNaN(num)) flow.setMaxMessagesPerGroup(num);
                }}
                onBlur={(event) => {
                  if (event.target.value === "") {
                    flow.setMaxMessagesPerGroup(50); // Reset to default on blur if empty
                  }
                }}
                disabled={flow.isSubmittingGroups || flow.isVerifyingGroups}
                className="border-outline-variant bg-surface h-10 w-28 rounded-lg border px-sm text-body-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
              />
            </label>
          </div>
        </div>

        <div className="border-outline-variant bg-surface-container-low mb-md rounded-xl border p-md">
          <div className="flex flex-wrap items-center justify-between gap-sm">
            <div>
              <div className="text-label-md text-on-surface-variant font-semibold uppercase">Nhóm đã lưu</div>
              <div className="text-body-sm text-on-surface-variant">Tổng nhóm: {flow.crawledGroupsTotal}</div>
            </div>
            <button
              type="button"
              className="border-outline-variant bg-surface hover:bg-surface-container-high inline-flex items-center gap-1 rounded-lg border px-md py-xs text-xs font-bold uppercase"
              onClick={() => setIsCrawledOpen((previous) => !previous)}
            >
              {isCrawledOpen ? "Thu gọn" : "Xem nhóm đã lưu"}
            </button>
          </div>

          {isCrawledOpen ? (
            <div className="mt-sm max-h-72 overflow-y-auto pr-1">
              {flow.isLoadingCrawledGroups ? (
                <div className="text-body-sm text-on-surface-variant">Đang tải nhóm đã lưu...</div>
              ) : flow.crawledGroupsError ? (
                <div className="border-error-container bg-error-container/40 text-error rounded-lg border px-md py-sm text-body-sm">
                  {flow.crawledGroupsError}
                </div>
              ) : flow.crawledGroups.length === 0 ? (
                <div className="text-body-sm text-on-surface-variant">Chưa có nhóm nào được lưu.</div>
              ) : (
                <div className="grid gap-sm sm:grid-cols-2">
                  {flow.crawledGroups.map((group) => (
                    <button
                      key={`${group.group_name}-${group.sheet_tab}`}
                      type="button"
                      className="border-outline-variant bg-surface hover:bg-surface-container-high rounded-lg border px-md py-sm text-left transition"
                      onClick={() => flow.addCrawledGroup(group)}
                    >
                      <div className="text-body-sm font-semibold text-on-surface">{group.group_name}</div>
                      <div className="text-body-sm text-on-surface-variant">Tin nhắn đã lưu: {group.message_count}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </div>

        <div className={!flow.hasConfirmedSession ? "opacity-70" : undefined}>
          <ZaloLiveGroupPicker flow={flow} />

          <ZaloGroupInputList
            rows={flow.groupRows}
            disabled={!flow.hasConfirmedSession || flow.isSubmittingGroups || flow.isVerifyingGroups}
            verifying={flow.isVerifyingGroups}
            onAddRow={flow.addGroupRow}
            onVerifyRows={() => void flow.verifyGroupRows()}
            onUpdateRow={flow.updateGroupRow}
            onRemoveRow={flow.removeGroupRow}
          />
        </div>
      </div>
    </section>
  );
}
