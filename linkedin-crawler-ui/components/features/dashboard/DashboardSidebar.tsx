"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { MaterialIcon } from "@/components/ui";
import { useAppPlatform } from "@/components/providers/AppPlatformProvider";
import { cn } from "@/lib/utils";
import { loginLinkedIn, verifyLinkedInOtp } from "@/services/linkedinCrawlerService";

import { DashboardPlatformSwitcher } from "./DashboardPlatformSwitcher";
import { useDashboard } from "./dashboard-context";

const sideActive =
  "flex items-center gap-3 border-r-4 border-sky-700 bg-slate-50 px-4 py-3 font-sans text-xs font-bold tracking-wider text-sky-700 uppercase transition-all duration-150 active:scale-95 dark:border-sky-400 dark:bg-zinc-800/50 dark:text-sky-400";
const sideIdle =
  "flex items-center gap-3 px-4 py-3 font-sans text-xs font-bold tracking-wider text-slate-500 uppercase transition-all duration-150 hover:bg-slate-50 hover:text-sky-600 active:scale-95 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-sky-300";

export function DashboardSidebar() {
  const d = useDashboard();
  const { platform } = useAppPlatform();
  const pathname = usePathname();
  const router = useRouter();
  const isHome = pathname === "/";
  const isGroupMgmt = pathname === "/quan-ly-nhom";
  const isTeamAdmin = pathname === "/admin/team";
  /** Leader LinkedIn: chỉ dùng màn quản lý đội, không dùng Post Feed / Groups. */
  const isLeaderLinkedInWorkspace = platform === "linkedin" && d.role === "leader";
  const [accountOpen, setAccountOpen] = useState(false);
  const [draftEmail, setDraftEmail] = useState("");
  const [draftPassword, setDraftPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [accountBusy, setAccountBusy] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [otpCode, setOtpCode] = useState("");
  const [pendingOtpSessionId, setPendingOtpSessionId] = useState<string | null>(
    null,
  );
  const [pendingCheckpointUrl, setPendingCheckpointUrl] = useState<string | null>(
    null,
  );
  const [isSwitchingAccount, setIsSwitchingAccount] = useState(false);
  const [switchingRole, setSwitchingRole] = useState<"leader" | "member">("member");
  const [switchingCode, setSwitchingCode] = useState("");

  const openAccountModal = () => {
    setDraftEmail(d.email);
    setDraftPassword(d.password);
    setShowPassword(false);
    setAccountError(null);
    setOtpCode("");
    setPendingOtpSessionId(null);
    setPendingCheckpointUrl(null);
    setIsSwitchingAccount(false);
    setAccountOpen(true);
  };

  const submitAccount = async () => {
    const email = draftEmail.trim();
    const password = draftPassword;
    if (!email || !password.trim()) {
      setAccountError("Vui lòng nhập đầy đủ email và mật khẩu.");
      return;
    }
    setAccountBusy(true);
    setAccountError(null);
    try {
      if (isSwitchingAccount) {
        await d.handleSwitchAccount(email, password, switchingRole, switchingCode);
        if (platform === "linkedin") {
          if (switchingRole === "leader") {
            router.replace("/admin/team");
          } else {
            router.replace("/");
          }
        }
        setAccountOpen(false);
        return;
      }

      const loginResponse = await loginLinkedIn({
        email,
        password,
        forceRelogin: true,
      });
      if (!loginResponse.success) {
        throw new Error(loginResponse.message || "Đăng nhập LinkedIn thất bại.");
      }
      const requiresOtp =
        loginResponse.need_otp === true ||
        loginResponse.login_step === "need_otp" ||
        ((loginResponse.checkpoint_url ?? "").trim().length > 0 &&
          (loginResponse.session_id ?? "").trim().length > 0);
      if (requiresOtp) {
        if (!loginResponse.session_id) {
          throw new Error(
            "Backend yêu cầu OTP nhưng chưa trả session_id. Vui lòng thử lại.",
          );
        }
        setPendingOtpSessionId(loginResponse.session_id);
        setPendingCheckpointUrl(loginResponse.checkpoint_url ?? null);
        setAccountError("LinkedIn yêu cầu mã xác minh. Nhập mã OTP rồi bấm Xác minh OTP.");
        return;
      }
      await d.applyAccountCredentials(email, password, loginResponse.session_id);
      setAccountOpen(false);
    } catch (error) {
      setAccountError(
        error instanceof Error ? error.message : "Cập nhật tài khoản thất bại.",
      );
    } finally {
      setAccountBusy(false);
    }
  };

  const submitOtpVerification = async () => {
    if (!pendingOtpSessionId) {
      setAccountError("Không tìm thấy phiên OTP. Vui lòng thử đăng nhập lại.");
      return;
    }
    if (!otpCode.trim()) {
      setAccountError("Vui lòng nhập mã OTP.");
      return;
    }
    setAccountBusy(true);
    setAccountError(null);
    try {
      const response = await verifyLinkedInOtp({
        sessionId: pendingOtpSessionId,
        otp: otpCode.trim(),
        checkpointUrl: pendingCheckpointUrl ?? undefined,
      });
      if (!response.success) {
        throw new Error(response.message || "Xác minh OTP thất bại.");
      }
      await d.applyAccountCredentials(
        draftEmail.trim(),
        draftPassword,
        response.session_id,
      );
      setPendingOtpSessionId(null);
      setPendingCheckpointUrl(null);
      setOtpCode("");
      setAccountOpen(false);
    } catch (error) {
      setAccountError(
        error instanceof Error ? error.message : "Xác minh OTP thất bại.",
      );
    } finally {
      setAccountBusy(false);
    }
  };

  return (
    <aside className="fixed top-0 left-0 z-40 hidden h-screen w-64 flex-col border-r border-slate-200 bg-white pt-20 lg:flex dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-8 flex items-center gap-3 px-6">
        <div className="bg-primary-container flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-white">
          <MaterialIcon name="radar" />
        </div>
        <div>
          <h2 className="text-lg leading-tight font-black text-slate-900 dark:text-zinc-100">
            CrawlerPro
          </h2>
          <p className="text-on-surface-variant mt-0.5 font-sans text-[10px] font-bold tracking-wider uppercase">
            {platform === "linkedin" ? "LinkedIn" : "Facebook"} workspace
          </p>
        </div>
      </div>
      <DashboardPlatformSwitcher />
      <nav className="flex-1 space-y-1 overflow-y-auto px-2">
        {isLeaderLinkedInWorkspace ? (
          <Link
            href="/admin/team"
            className={cn(isTeamAdmin ? sideActive : sideIdle)}
          >
            <MaterialIcon name="group_add" className="shrink-0" />
            <span className="min-w-0 leading-snug">Quản lý đội ngũ</span>
          </Link>
        ) : (
          <>
            <Link href="/" className={cn(isHome ? sideActive : sideIdle)}>
              <MaterialIcon name="radar" className="shrink-0" />
              <span className="min-w-0 leading-snug">Post Feed</span>
            </Link>
            <Link
              href="/quan-ly-nhom"
              className={cn(isGroupMgmt ? sideActive : sideIdle)}
            >
              <MaterialIcon name="group" className="shrink-0" />
              <span className="min-w-0 leading-snug">Groups</span>
            </Link>
            {d.role === "leader" && (
              <Link
                href="/admin/team"
                className={cn(isTeamAdmin ? sideActive : sideIdle)}
              >
                <MaterialIcon name="group_add" className="shrink-0" />
                <span className="min-w-0 leading-snug">Quản lý đội ngũ</span>
              </Link>
            )}
          </>
        )}
      </nav>
      
      <div className="space-y-1 p-2">
        {platform === "linkedin" ? (
          <button
            type="button"
            onClick={openAccountModal}
            className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left font-sans text-xs font-bold tracking-wider text-slate-500 uppercase transition-all hover:bg-slate-50 dark:text-zinc-400"
          >
            <MaterialIcon name="account_circle" className="shrink-0" />
            <span className="min-w-0 leading-snug">Tài khoản LinkedIn</span>
          </button>
        ) : (
          <p className="text-on-surface-variant px-4 py-3 font-sans text-[10px] leading-snug tracking-wide uppercase">
            Đăng nhập / tài khoản Facebook do team Facebook tích hợp khi cần.
          </p>
        )}
      </div>

      {accountOpen ? (
        <div
          className="fixed inset-0 z-[70] flex items-end justify-center p-md sm:items-center"
          role="presentation"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45 backdrop-blur-[1px]"
            aria-label="Đóng"
            onClick={() => !accountBusy && setAccountOpen(false)}
          />
          <div
            className="border-outline-variant bg-surface relative z-10 w-[min(92vw,520px)] rounded-xl border p-lg shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="account-modal-title"
          >
            <h3 id="account-modal-title" className="text-h3 text-on-surface font-semibold">
              Cập nhật tài khoản
            </h3>
            <div className="flex items-center justify-between mt-xs">
              <p className="text-body-sm text-on-surface-variant">
                Sau khi xác nhận, hệ thống sẽ làm mới dữ liệu từ get-all-posts và danh sách nhóm.
              </p>
              {!isSwitchingAccount && (
                <button 
                  type="button"
                  className="text-primary text-xs font-bold uppercase hover:underline"
                  onClick={() => {
                    setIsSwitchingAccount(true);
                    setDraftEmail("");
                    setDraftPassword("");
                    setAccountError(null);
                  }}
                >
                  Chuyển đổi tài khoản
                </button>
              )}
            </div>

            {isSwitchingAccount && (
              <div className="mt-md p-md rounded-lg bg-primary/5 border border-primary/20 space-y-md animate-in fade-in slide-in-from-top-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-label-md font-bold uppercase text-primary">Chế độ chuyển đổi</h4>
                  <button 
                    onClick={() => setIsSwitchingAccount(false)}
                    className="text-on-surface-variant hover:text-error transition-colors"
                  >
                    <MaterialIcon name="close" className="text-lg" />
                  </button>
                </div>
                
                <div className="flex items-center gap-lg">
                  <label className="flex items-center gap-xs cursor-pointer">
                    <input 
                      type="radio" 
                      name="role" 
                      className="accent-primary"
                      checked={switchingRole === "member"}
                      onChange={() => setSwitchingRole("member")}
                    />
                    <span className="text-body-sm font-bold">Thành viên</span>
                  </label>
                  <label className="flex items-center gap-xs cursor-pointer">
                    <input 
                      type="radio" 
                      name="role" 
                      className="accent-primary"
                      checked={switchingRole === "leader"}
                      onChange={() => setSwitchingRole("leader")}
                    />
                    <span className="text-body-sm font-bold">Leader</span>
                  </label>
                </div>

                {switchingRole === "leader" && (
                  <div className="flex flex-col gap-base">
                    <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                      Mã xác nhận Leader
                    </label>
                    <input
                      className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                      type="password"
                      placeholder="Nhập mã leader"
                      value={switchingCode}
                      onChange={(e) => setSwitchingCode(e.target.value)}
                    />
                  </div>
                )}
              </div>
            )}

            <div className="mt-md flex flex-col gap-md">
              <div className="flex flex-col gap-base">
                <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                  Email
                </label>
                <input
                  className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                  type="email"
                  value={draftEmail}
                  onChange={(e) => setDraftEmail(e.target.value)}
                  disabled={accountBusy}
                  autoComplete="username"
                />
              </div>
              <div className="flex flex-col gap-base">
                <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                  Mật khẩu
                </label>
                <div className="relative">
                  <input
                    className="border-outline-variant bg-surface focus:border-primary focus:ring-primary w-full rounded-lg border px-md py-sm pr-12 transition-all outline-none focus:ring-1"
                    type={showPassword ? "text" : "password"}
                    value={draftPassword}
                    onChange={(e) => setDraftPassword(e.target.value)}
                    disabled={accountBusy}
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    className="text-on-surface-variant hover:text-on-surface absolute top-1/2 right-2 -translate-y-1/2 rounded px-2 py-1 text-xs font-bold uppercase"
                    onClick={() => setShowPassword((v) => !v)}
                    disabled={accountBusy}
                    aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  >
                    {showPassword ? "Ẩn" : "Hiện"}
                  </button>
                </div>
              </div>
              {pendingOtpSessionId ? (
                <div className="flex flex-col gap-base">
                  <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                    Mã OTP xác minh
                  </label>
                  <input
                    className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                    type="text"
                    inputMode="numeric"
                    placeholder="Nhập mã từ email LinkedIn"
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value)}
                    disabled={accountBusy}
                  />
                </div>
              ) : null}
            </div>

            {accountError ? (
              <div className="border-error-container bg-error-container/40 text-error mt-md rounded-lg border px-md py-sm text-body-sm">
                {accountError}
              </div>
            ) : null}

            <div className="mt-lg flex justify-end gap-sm">
              <button
                type="button"
                className="text-on-surface-variant rounded-lg px-md py-sm text-sm font-bold uppercase"
                onClick={() => setAccountOpen(false)}
                disabled={accountBusy}
              >
                Hủy
              </button>
              <button
                type="button"
                className="bg-primary text-on-primary hover:bg-primary-container rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
                onClick={() => void submitAccount()}
                disabled={accountBusy || !!pendingOtpSessionId}
              >
                {accountBusy ? "Đang xác nhận..." : "Xác nhận"}
              </button>
              {pendingOtpSessionId ? (
                <button
                  type="button"
                  className="bg-secondary text-on-secondary hover:bg-secondary-container rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => void submitOtpVerification()}
                  disabled={accountBusy}
                >
                  {accountBusy ? "Đang xác minh..." : "Xác minh OTP"}
                </button>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </aside>
  );
}
