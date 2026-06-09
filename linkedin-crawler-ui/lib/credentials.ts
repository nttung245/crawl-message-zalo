"use client";

export type CredentialRecord = {
  id: string;
  email: string;
  password?: string;
  name?: string;
  avatar?: string;
  status?: "connected" | "disconnected" | "error";
  phone?: string;
  platform?: "linkedin" | "facebook" | "zalo";
};

const ACCOUNTS_STORAGE_KEY = "linkedin_multi_accounts";
const ACTIVE_ACCOUNT_ID_KEY = "linkedin_active_account_id";

function getAccountsFromStorage(): CredentialRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(ACCOUNTS_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveAccountsToStorage(accounts: CredentialRecord[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCOUNTS_STORAGE_KEY, JSON.stringify(accounts));
}

export function getAllLinkedInAccounts(): CredentialRecord[] {
  return getAccountsFromStorage();
}

export function saveLinkedInAccount(account: CredentialRecord): void {
  const accounts = getAccountsFromStorage();
  const existingIndex = accounts.findIndex((a) => a.email === account.email);
  if (existingIndex >= 0) {
    accounts[existingIndex] = { ...accounts[existingIndex], ...account };
  } else {
    accounts.push({
      ...account,
      id: account.id || Math.random().toString(36).substring(2, 9),
    });
  }
  saveAccountsToStorage(accounts);
}

export function removeLinkedInAccount(email: string): void {
  const accounts = getAccountsFromStorage();
  saveAccountsToStorage(accounts.filter((a) => a.email !== email));
}

// Keep backward compatibility for single active account logic
export function readLinkedInCredentials(): CredentialRecord | null {
  const accounts = getAccountsFromStorage();
  if (typeof window === "undefined") return accounts[0] || null;
  const activeId = localStorage.getItem(ACTIVE_ACCOUNT_ID_KEY);
  if (activeId) {
    const active = accounts.find((a) => a.id === activeId);
    if (active) return active;
  }
  return accounts[0] || null;
}

export function writeLinkedInCredentials(email: string, password?: string): void {
  saveLinkedInAccount({ id: email, email, password, status: "connected" });
  if (typeof window !== "undefined") {
    localStorage.setItem(ACTIVE_ACCOUNT_ID_KEY, email);
  }
}

export function setActiveAccount(id: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(ACTIVE_ACCOUNT_ID_KEY, id);
  }
}

export function clearLinkedInCredentials(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCOUNTS_STORAGE_KEY);
  localStorage.removeItem(ACTIVE_ACCOUNT_ID_KEY);
}
