"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import { MaterialIcon } from "@/components/ui";
import {
  readLinkedInCredentials,
  writeLinkedInCredentials,
} from "@/lib/credentials";

interface DashboardAuthGateProps {
  email: string;
  password: string;
  setEmail: (v: string) => void;
  setPassword: (v: string) => void;
  children: ReactNode;
}

export function DashboardAuthGate({
  email,
  password,
  setEmail,
  setPassword,
  children,
}: DashboardAuthGateProps) {
  const pathname = usePathname();
  const [isReady, setIsReady] = useState(false);
  const [localEmail, setLocalEmail] = useState(email);
  const [localPassword, setLocalPassword] = useState(password);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const hasCredentials = useMemo(
    () => Boolean(email.trim() && password.trim()),
    [email, password],
  );
  const bypassLinkedInAuth = pathname.startsWith("/zalo-crawl");

  useEffect(() => {
    if (hasCredentials) {
      setIsReady(true);
      return;
    }
    const stored = readLinkedInCredentials();
    if (stored?.email && stored?.password) {
      setEmail(stored.email);
      setPassword(stored.password);
      setLocalEmail(stored.email);
      setLocalPassword(stored.password);
      setIsReady(true);
      return;
    }
    setIsReady(false);
  }, [hasCredentials, setEmail, setPassword]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const nextEmail = localEmail.trim();
    const nextPassword = localPassword.trim();
    if (!nextEmail || !nextPassword) {
      setErrorMessage("Vui lòng nhập đầy đủ email và mật khẩu LinkedIn.");
      return;
    }
    writeLinkedInCredentials(nextEmail, nextPassword);
    setEmail(nextEmail);
    setPassword(nextPassword);
    setErrorMessage(null);
    setIsReady(true);
  };

  if (bypassLinkedInAuth || isReady) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-background text-on-background">
      <div className="mx-auto flex min-h-screen w-full max-w-[1024px] flex-col items-stretch justify-center px-lg py-xl">
        <div className="border-outline-variant bg-surface-container-lowest mx-auto w-full max-w-[640px] rounded-2xl border p-xl shadow-lg">
          <div className="mb-lg flex items-center gap-3">
            <div className="bg-primary/10 text-primary flex h-12 w-12 items-center justify-center rounded-full">
              <MaterialIcon name="lock" className="text-2xl" />
            </div>
            <div className="min-w-0">
              <h1 className="text-h1 text-on-surface font-semibold">
                Xác thực LinkedIn
              </h1>
              <p className="text-body-sm text-on-surface-variant">
                Nhập email và mật khẩu để lưu vào cookie, giúp các API filter và
                get all posts hoạt động ổn định.
              </p>
            </div>
          </div>

          <form className="flex flex-col gap-md" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-base">
              <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                Email LinkedIn
              </label>
              <input
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                type="email"
                placeholder="email@congty.com"
                value={localEmail}
                onChange={(e) => setLocalEmail(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div className="flex flex-col gap-base">
              <label className="text-label-md text-on-surface-variant font-semibold tracking-wide uppercase">
                Mật khẩu
              </label>
              <input
                className="border-outline-variant bg-surface focus:border-primary focus:ring-primary rounded-lg border px-md py-sm transition-all outline-none focus:ring-1"
                type="password"
                placeholder="••••••••••••"
                value={localPassword}
                onChange={(e) => setLocalPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            {errorMessage && (
              <div className="border-error-container bg-error-container/40 text-error rounded-lg border px-md py-sm text-body-sm">
                {errorMessage}
              </div>
            )}

            <button
              type="submit"
              className="bg-primary text-on-primary hover:bg-primary-container active:scale-[0.98] w-full rounded-lg py-sm font-bold transition-all"
            >
              Lưu thông tin & tiếp tục
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
