"use client";

type CredentialRecord = {
  email: string;
  password: string;
};

const EMAIL_COOKIE = "linkedin_email";
const PASSWORD_COOKIE = "linkedin_password";
const DEFAULT_MAX_AGE_DAYS = 7;

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const cookies = document.cookie.split(";");
  for (const raw of cookies) {
    const [key, ...rest] = raw.trim().split("=");
    if (key === name) {
      return decodeURIComponent(rest.join("="));
    }
  }
  return null;
}

function writeCookie(name: string, value: string, maxAgeDays: number): void {
  if (typeof document === "undefined") return;
  const maxAge = Math.max(1, Math.floor(maxAgeDays * 24 * 60 * 60));
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; samesite=lax`;
}

export function readLinkedInCredentials(): CredentialRecord | null {
  const email = readCookie(EMAIL_COOKIE) ?? "";
  const password = readCookie(PASSWORD_COOKIE) ?? "";
  if (!email || !password) {
    return null;
  }
  return { email, password };
}

export function writeLinkedInCredentials(
  email: string,
  password: string,
  maxAgeDays: number = DEFAULT_MAX_AGE_DAYS,
): void {
  if (!email || !password) return;
  writeCookie(EMAIL_COOKIE, email, maxAgeDays);
  writeCookie(PASSWORD_COOKIE, password, maxAgeDays);
}

export function clearLinkedInCredentials(): void {
  writeCookie(EMAIL_COOKIE, "", -1);
  writeCookie(PASSWORD_COOKIE, "", -1);
}
