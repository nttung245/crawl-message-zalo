"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { MaterialIcon } from "@/components/ui";
import type { ZaloCrawlerFlowValue } from "@/hooks/useZaloCrawlerFlow";
import { getZaloInboxReport } from "@/services/zaloCrawlerService";
import type { ZaloInboxReportResponse } from "@/types/zalo-api";

const ACCOUNT_OWNER_ID = "default";

interface ZaloAccountManagerPanelProps {
  flow: ZaloCrawlerFlowValue;
}

function formatTime(value?: string | null) {
  if (!value) return "Chưa có";
  const num = Number(value);
  const date = !Number.isNaN(num) && String(num) === String(value).trim() ? new Date(num) : new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function ZaloAccountManagerPanel({ flow }: ZaloAccountManagerPanelProps) {
  const [label, setLabel] = useState("");
  const [phone, setPhone] = useState("");
  const [report, setReport] = useState<ZaloInboxReportResponse | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [isLoadingReport, setIsLoadingReport] = useState(false);

  const selectedAccount = useMemo(
    () => flow.accounts.find((account) => account.account_id === flow.userId),
    [flow.accounts, flow.userId],
  );

  const loadReport = useCallback(async () => {
    setIsLoadingReport(true);
    setReportError(null);
    try {
      const response = await getZaloInboxReport(ACCOUNT_OWNER_ID, flow.accounts.map((account) => account.account_id));
      setReport(response);
    } catch (error) {
      setReportError(error instanceof Error ? error.message : "Khong the tai bao cao inbox.");
    } finally {
      setIsLoadingReport(false);
    }
  }, [flow.accounts, flow.userId]);

  useEffect(() => {
    void loadReport();
    const timer = window.setInterval(() => {
      void loadReport();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [loadReport]);

  async function handleCreateAccount() {
    await flow.createAccount(label, phone);
    setLabel("");
    setPhone("");
  }

  return (
    <section className="grid gap-lg xl:grid-cols-[380px_1fr]">
      <div className="border-outline-variant bg-surface-container-lowest rounded-2xl border p-lg shadow-sm">
        <div className="mb-md">
          <h2 className="text-h2 font-semibold text-on-surface">Tai khoan Zalo</h2>
          <p className="text-body-sm text-on-surface-variant">
            Moi account slot co session, listener va du lieu Supabase rieng. Mot ban MKT co the quan ly nhieu Zalo ca nhan tai day.
          </p>
        </div>

        <div className="mb-md grid gap-sm">
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Ten account, vi du: MKT 01"
            className="border-outline-variant bg-surface rounded-lg border px-md py-sm text-body-sm"
          />
          <input
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="So dien thoai neu can"
            className="border-outline-variant bg-surface rounded-lg border px-md py-sm text-body-sm"
          />
          <button
            type="button"
            onClick={() => void handleCreateAccount()}
            className="bg-primary text-on-primary inline-flex items-center justify-center gap-sm rounded-lg px-md py-sm text-body-sm font-semibold"
          >
            <MaterialIcon name="add" className="text-base" />
            Them account
          </button>
        </div>

        {flow.accountsError ? (
          <div className="border-error-container bg-error-container/40 text-error mb-md rounded-lg border px-md py-sm text-body-sm">
            {flow.accountsError}
          </div>
        ) : null}

        <div className="flex flex-col gap-sm">
          {flow.accounts.map((account) => {
            const active = account.account_id === flow.userId;
            const listener = account.listener;
            return (
              <article
                key={account.account_id}
                className={`rounded-xl border p-md ${
                  active
                    ? "border-primary bg-primary-container text-on-primary-container"
                    : "border-outline-variant bg-surface"
                }`}
              >
                <div className="mb-sm flex items-start justify-between gap-sm">
                  <div>
                    <div className="font-semibold">{account.label || account.account_id}</div>
                    <div className="text-body-sm opacity-80">{account.account_id}</div>
                    <div className="text-body-sm opacity-80">
                      Auth: {account.has_auth ? "da login" : "chua login"} · Listener: {listener?.connected ? "online" : listener?.running ? "dang chay" : "off"}
                    </div>
                    <div className="text-body-sm opacity-80">Tin da thay: {listener?.messages_seen ?? 0}</div>
                  </div>
                  {active ? (
                    <span className="rounded-full bg-secondary-container px-sm py-0.5 text-xs font-semibold text-on-secondary-container">
                      Dang chon
                    </span>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-sm">
                  <button
                    type="button"
                    onClick={() => flow.switchAccount(account.account_id)}
                    className="border-outline-variant bg-surface rounded-lg border px-sm py-xs text-body-sm font-semibold"
                  >
                    Chon
                  </button>
                  <button
                    type="button"
                    onClick={() => void flow.deleteAccount(account.account_id, false)}
                    className="border-error-container text-error rounded-lg border px-sm py-xs text-body-sm font-semibold"
                  >
                    An
                  </button>
                </div>
              </article>
            );
          })}
          {flow.accounts.length === 0 && !flow.isLoadingAccounts ? (
            <div className="border-outline-variant rounded-xl border px-md py-lg text-body-sm text-on-surface-variant">
              Chua co account nao. Tao account slot roi bam Hien QR dang nhap.
            </div>
          ) : null}
        </div>
      </div>

      <div className="border-outline-variant bg-surface-container-lowest rounded-2xl border p-lg shadow-sm">
        <div className="mb-md flex flex-wrap items-start justify-between gap-sm">
          <div>
            <h2 className="text-h2 font-semibold text-on-surface">Bao cao inbox MKT</h2>
            <p className="text-body-sm text-on-surface-variant">
              Tong hop tu tin nhan listener/crawl theo tung account Zalo.
              {selectedAccount ? ` Dang xem: ${selectedAccount.label}.` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadReport()}
            disabled={isLoadingReport}
            className="border-outline-variant bg-surface inline-flex items-center gap-sm rounded-lg border px-md py-sm text-body-sm font-semibold disabled:opacity-60"
          >
            <MaterialIcon name="refresh" className="text-base" />
            Tai lai
          </button>
        </div>

        {reportError ? (
          <div className="border-error-container bg-error-container/40 text-error mb-md rounded-lg border px-md py-sm text-body-sm">
            {reportError}
          </div>
        ) : null}

        <div className="mb-md grid gap-sm md:grid-cols-3">
          <div className="rounded-xl border border-outline-variant bg-surface p-md">
            <div className="text-body-sm text-on-surface-variant">Tin nhan</div>
            <div className="text-h2 font-semibold">{report?.total_messages ?? 0}</div>
          </div>
          <div className="rounded-xl border border-outline-variant bg-surface p-md">
            <div className="text-body-sm text-on-surface-variant">Khach/conversation</div>
            <div className="text-h2 font-semibold">{report?.total_customers ?? 0}</div>
          </div>
          <div className="rounded-xl border border-outline-variant bg-surface p-md">
            <div className="text-body-sm text-on-surface-variant">Account dang chon</div>
            <div className="text-body-md font-semibold">{selectedAccount?.label ?? flow.userId}</div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-body-sm">
            <thead className="border-b border-outline-variant text-on-surface-variant">
              <tr>
                <th className="py-sm pr-md">Account</th>
                <th className="py-sm pr-md">Khach / hoi thoai</th>
                <th className="py-sm pr-md">Tin</th>
                <th className="py-sm pr-md">Gui</th>
                <th className="py-sm pr-md">Nhan</th>
                <th className="py-sm pr-md">Gan nhat</th>
                <th className="py-sm">Noi dung moi</th>
              </tr>
            </thead>
            <tbody>
              {(report?.customers ?? []).map((row) => (
                <tr key={`${row.account_id}-${row.customer_id}`} className="border-b border-outline-variant">
                  <td className="py-sm pr-md font-semibold">{row.account_label}</td>
                  <td className="py-sm pr-md">{row.conversation_name || row.customer_name}</td>
                  <td className="py-sm pr-md">{row.message_count}</td>
                  <td className="py-sm pr-md">{row.sent_count}</td>
                  <td className="py-sm pr-md">{row.received_count}</td>
                  <td className="py-sm pr-md">{formatTime(row.latest_message_at)}</td>
                  <td className="max-w-md truncate py-sm">{row.latest_content || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {report && report.customers.length === 0 ? (
            <div className="py-lg text-body-sm text-on-surface-variant">
              Chua co du lieu inbox cho cac account nay.
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
