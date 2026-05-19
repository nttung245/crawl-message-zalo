"use client";

import { MaterialIcon } from "@/components/ui";
import type { ZaloAuthStatus } from "@/types/zalo-api";

interface ZaloQrLoginModalProps {
  open: boolean;
  qrBase64: string | null;
  authStatus: ZaloAuthStatus | null;
  expiresAt: number | null;
  isRefreshingQr: boolean;
  onRefreshQr: () => Promise<void>;
  onClose: () => Promise<void>;
}

function formatExpiry(expiresAt: number | null): string {
  if (!expiresAt) return "Chưa có";

  const expiryDate = new Date(expiresAt);
  const hours = String(expiryDate.getHours()).padStart(2, "0");
  const minutes = String(expiryDate.getMinutes()).padStart(2, "0");
  const seconds = String(expiryDate.getSeconds()).padStart(2, "0");

  return `${hours}:${minutes}:${seconds}`;
}

function authStatusLabel(status: ZaloAuthStatus | null): string {
  switch (status) {
    case "waiting_scan":
      return "Đang chờ quét QR";
    case "confirmed":
      return "Đăng nhập thành công";
    case "qr_expired":
      return "QR đã hết hạn";
    default:
      return "Chưa có trạng thái";
  }
}

export function ZaloQrLoginModal({
  open,
  qrBase64,
  authStatus,
  expiresAt,
  isRefreshingQr,
  onRefreshQr,
  onClose,
}: ZaloQrLoginModalProps) {
  const expiresAtLabel = open ? formatExpiry(expiresAt) : "Chưa có";

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-end justify-center p-md sm:items-center"
      role="presentation"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/45 backdrop-blur-[1px]"
        aria-label="Đóng"
        onClick={() => void onClose()}
      />

      <div
        className="border-outline-variant bg-surface relative z-10 flex w-[min(94vw,760px)] flex-col gap-lg rounded-2xl border p-lg shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="zalo-qr-login-title"
      >
        <div className="flex items-start justify-between gap-md">
          <div className="space-y-xs">
            <h2
              id="zalo-qr-login-title"
              className="text-h2 text-on-surface font-semibold"
            >
              Đăng nhập Zalo bằng QR
            </h2>
            <p className="text-body-sm text-on-surface-variant">
              Mở Zalo trên điện thoại, quét QR và xác nhận đăng nhập để bắt đầu phiên crawl.
            </p>
          </div>
          <div className="bg-surface-container-low text-on-surface rounded-full px-md py-xs text-xs font-bold uppercase">
            {authStatusLabel(authStatus)}
          </div>
        </div>

        <div className="grid gap-lg lg:grid-cols-[280px_minmax(0,1fr)]">
          <div className="border-outline-variant bg-surface-container-low flex min-h-[280px] items-center justify-center rounded-2xl border p-md">
            {qrBase64 ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={qrBase64}
                alt="QR đăng nhập Zalo"
                className="h-full max-h-[248px] w-full max-w-[248px] rounded-xl object-contain"
              />
            ) : (
              <div className="text-body-sm text-on-surface-variant text-center">
                Chưa có ảnh QR để hiển thị.
              </div>
            )}
          </div>

          <div className="flex flex-col gap-md">
            <div className="border-outline-variant bg-surface-container-low rounded-2xl border p-md">
              <div className="mb-sm flex items-center gap-2">
                <MaterialIcon name="info" className="text-primary" />
                <h3 className="text-h3 font-semibold">Hướng dẫn nhanh</h3>
              </div>
              <ol className="text-body-sm text-on-surface-variant flex list-decimal flex-col gap-2 pl-lg">
                <li>Mở Zalo trên điện thoại.</li>
                <li>Chọn quét mã QR trong ứng dụng.</li>
                <li>Xác nhận đăng nhập trên thiết bị để mở phiên crawler.</li>
              </ol>
            </div>

            <div className="grid gap-sm sm:grid-cols-2">
              <div className="border-outline-variant bg-surface rounded-xl border p-md">
                <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
                  Trạng thái
                </div>
                <div className="text-body-md text-on-surface font-semibold">
                  {authStatusLabel(authStatus)}
                </div>
              </div>
              <div className="border-outline-variant bg-surface rounded-xl border p-md">
              <div className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
                  Hết hạn lúc
              </div>
              <div className="text-body-md text-on-surface font-semibold">
                  {authStatus === "qr_expired" ? "Đã hết hạn" : expiresAtLabel}
              </div>
            </div>
            </div>

            {authStatus === "confirmed" ? (
              <div className="border-secondary-container bg-secondary-container/20 text-on-secondary-container rounded-xl border px-md py-sm text-body-sm">
                Phiên Zalo đã sẵn sàng. Modal sẽ đóng, sau đó có thể thêm nhóm và chạy crawl.
              </div>
            ) : null}

            {authStatus === "qr_expired" ? (
              <div className="border-error-container bg-error-container/40 text-error rounded-xl border px-md py-sm text-body-sm">
                QR đã hết hạn. Làm mới mã để tiếp tục đăng nhập.
              </div>
            ) : null}

            <div className="mt-auto flex flex-wrap justify-end gap-sm">
              <button
                type="button"
                className="rounded-lg px-md py-sm text-sm font-bold uppercase text-on-surface-variant"
                onClick={() => void onClose()}
              >
                Đóng
              </button>
              <button
                type="button"
                className="bg-primary text-on-primary hover:bg-primary-container inline-flex items-center gap-2 rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void onRefreshQr()}
                disabled={isRefreshingQr || authStatus === "confirmed"}
              >
                <MaterialIcon name="refresh" className="text-base" />
                {isRefreshingQr ? "Đang làm mới..." : "Làm mới QR"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
