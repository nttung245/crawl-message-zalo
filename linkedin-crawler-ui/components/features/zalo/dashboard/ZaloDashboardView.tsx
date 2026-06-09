"use client";

import { MaterialIcon } from "@/components/ui";
import type { ZaloCrawlerFlowValue } from "@/hooks/useZaloCrawlerFlow";
import { useState } from "react";
import Image from "next/image";

interface ZaloDashboardViewProps {
  flow: ZaloCrawlerFlowValue;
  onEnterChat: (accountId: string) => void;
}

function shortId(value: string, head = 10, tail = 6) {
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function accountStatus(account: ZaloCrawlerFlowValue["accounts"][number]) {
  if (account.listener?.auth_expired) return { text: "Hết hạn — đăng nhập lại", tone: "error" as const };
  if (account.listener?.connected) return { text: "Online", tone: "success" as const };
  if (account.listener?.running) return { text: "Đang chạy", tone: "warning" as const };
  if (account.has_auth) return { text: "Đã kết nối", tone: "success" as const };
  return { text: "Chưa kết nối", tone: "muted" as const };
}

function StatusDot({ tone }: { tone: "success" | "warning" | "muted" | "error" }) {
  const className =
    tone === "success"
      ? "bg-green-500"
      : tone === "warning"
        ? "bg-amber-500"
        : tone === "error"
          ? "bg-red-500"
          : "bg-gray-300";
  return <span className={`inline-block h-3 w-3 rounded-full border-2 border-white ${className}`} />;
}

export function ZaloDashboardView({ flow, onEnterChat }: ZaloDashboardViewProps) {
  const [newAccountLabel, setNewAccountLabel] = useState("");
  const [newAccountPhone, setNewAccountPhone] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // States for Editing and Dropdown Menu
  const [activeMenuAccountId, setActiveMenuAccountId] = useState<string | null>(null);
  const [editingAccount, setEditingAccount] = useState<ZaloCrawlerFlowValue["accounts"][number] | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  async function handleCreateAccount() {
    const label = newAccountLabel.trim();
    if (!label) return;
    await flow.createAccount(label, newAccountPhone.trim() || undefined);
    setNewAccountLabel("");
    setNewAccountPhone("");
  }

  const filteredAccounts = flow.accounts.filter(acc => 
    (acc.label || "").toLowerCase().includes(searchQuery.toLowerCase()) ||
    (acc.phone || "").includes(searchQuery)
  );

  return (
    <div className="flex flex-col gap-lg">
      <header className="flex items-center justify-between gap-md border-b pb-md">
        <div className="flex items-center gap-sm">
          <h2 className="text-h2 font-semibold text-on-surface">Dashboard</h2>
          <span className="rounded-full bg-surface-container-high px-sm py-xs text-xs font-semibold text-on-surface-variant">
            {flow.accounts.length} tài khoản
          </span>
        </div>
        <div className="flex items-center gap-sm">
          <button className="border-outline-variant bg-surface inline-flex items-center gap-xs rounded-lg border px-md py-sm text-body-sm font-semibold hover:bg-surface-container-low transition">
            <MaterialIcon name="group_add" className="text-base" />
            Gộp tài khoản
          </button>
          <button className="bg-primary-container text-on-primary-container inline-flex items-center gap-xs rounded-lg px-md py-sm text-body-sm font-semibold hover:bg-primary/20 transition">
            <MaterialIcon name="support_agent" className="text-base" />
            Hỗ trợ
          </button>
          <div className="relative">
            <MaterialIcon name="search" className="absolute left-sm top-1/2 -translate-y-1/2 text-on-surface-variant" />
            <input
              type="text"
              placeholder="Tên, SĐT, UID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="border-outline-variant bg-surface rounded-lg border py-sm pl-10 pr-md text-body-sm min-w-[250px] focus:border-primary focus:outline-none"
            />
          </div>
        </div>
      </header>

      <div className="flex items-center gap-xs text-body-sm text-on-surface-variant">
        <MaterialIcon name="drag_indicator" className="text-base" />
        Kéo thả để sắp xếp thứ tự
      </div>

      <div className="border-outline-variant bg-surface rounded-xl border p-md mb-md">
        <h3 className="text-label-md font-semibold uppercase text-on-surface-variant mb-sm">Thêm tài khoản mới</h3>
        <div className="flex items-center gap-md">
          <input
            value={newAccountLabel}
            onChange={(event) => setNewAccountLabel(event.target.value)}
            placeholder="Tên tài khoản (vd: Nam, Mai...)"
            className="border-outline-variant bg-surface min-h-10 rounded-lg border px-md py-sm text-body-sm flex-1"
          />
          <input
            value={newAccountPhone}
            onChange={(event) => setNewAccountPhone(event.target.value)}
            placeholder="Số điện thoại"
            className="border-outline-variant bg-surface min-h-10 rounded-lg border px-md py-sm text-body-sm flex-1"
          />
          <button
            type="button"
            onClick={() => void handleCreateAccount()}
            disabled={!newAccountLabel.trim()}
            className="bg-primary text-on-primary inline-flex min-h-10 items-center justify-center gap-sm rounded-lg px-xl py-sm text-body-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60 transition hover:opacity-90"
          >
            <MaterialIcon name="add" className="text-base" />
            Thêm
          </button>
        </div>
        {flow.accountsError ? (
          <div className="border-error-container bg-error-container/40 text-error mt-md rounded-lg border px-md py-sm text-body-sm">
            {flow.accountsError}
          </div>
        ) : null}
      </div>

      <div className="grid gap-md sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {filteredAccounts.map((account) => {
          const status = accountStatus(account);
          return (
            <div key={account.account_id} className="border-outline-variant bg-surface-container-lowest flex flex-col rounded-2xl border p-md shadow-sm transition hover:shadow-md">
              <div className="flex items-start justify-between mb-md">
                <div className="relative">
                  <div className="h-12 w-12 rounded-full bg-surface-container-high flex items-center justify-center text-title-md font-semibold text-primary">
                    {account.label?.[0]?.toUpperCase() || "Z"}
                  </div>
                  <div className="absolute bottom-0 right-0">
                    <StatusDot tone={status.tone} />
                  </div>
                </div>
                
                {/* 3-Dot Menu Dropdown */}
                <div className="relative">
                  <button 
                    onClick={() => setActiveMenuAccountId(prev => prev === account.account_id ? null : account.account_id)}
                    className="text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-surface-container transition"
                  >
                    <MaterialIcon name="more_vert" />
                  </button>
                  
                  {activeMenuAccountId === account.account_id && (
                    <>
                      <div 
                        className="fixed inset-0 z-10" 
                        onClick={() => setActiveMenuAccountId(null)}
                      />
                      <div className="absolute right-0 mt-xs w-48 bg-surface-container-lowest border border-outline-variant rounded-lg shadow-lg py-1 z-20">
                        <button
                          onClick={() => {
                            setEditingAccount(account);
                            setEditLabel(account.label || "");
                            setEditPhone(account.phone || "");
                            setActiveMenuAccountId(null);
                          }}
                          className="w-full text-left px-md py-sm text-body-sm hover:bg-surface-container-low flex items-center gap-xs font-semibold text-on-surface"
                        >
                          <MaterialIcon name="edit" className="text-base text-primary" />
                          Chỉnh sửa
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Bạn có chắc muốn xóa hoàn toàn dữ liệu đăng nhập của ${account.label || account.account_id}?`)) {
                              void flow.deleteAccount(account.account_id, true);
                            }
                            setActiveMenuAccountId(null);
                          }}
                          className="w-full text-left px-md py-sm text-body-sm hover:bg-surface-container-low flex items-center gap-xs font-semibold text-error border-t border-outline-variant/30"
                        >
                          <MaterialIcon name="delete" className="text-base text-error" />
                          Xóa hoàn toàn Auth
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
              
              <div className="mb-sm">
                <div className="text-title-md font-semibold truncate">{account.label || "Tài khoản"}</div>
                <div className="text-body-sm text-on-surface-variant truncate opacity-80 mt-0.5">
                  UID: {shortId(account.account_id, 6, 4)}
                </div>
                <div className="text-body-sm text-on-surface-variant flex items-center gap-xs mt-1">
                  <MaterialIcon name="call" className="text-sm text-primary" />
                  {account.phone || "Chưa có SĐT"}
                </div>
              </div>

              <div className="mt-auto pt-sm flex gap-sm">
                <button 
                  onClick={() => onEnterChat(account.account_id)}
                  className="bg-primary text-on-primary flex-1 rounded-lg py-2 text-body-sm font-semibold transition hover:opacity-90"
                >
                  Chat
                </button>
                <button 
                  onClick={() => flow.deleteAccount(account.account_id, false)}
                  className="bg-surface-container text-on-surface flex-1 rounded-lg py-2 text-body-sm font-semibold transition hover:bg-surface-container-high"
                >
                  Ngắt kết nối
                </button>
              </div>
            </div>
          );
        })}
      </div>
      
      {filteredAccounts.length === 0 && !flow.isLoadingAccounts && (
        <div className="border-outline-variant bg-surface-container-lowest rounded-2xl border p-xl text-center text-on-surface-variant">
          <MaterialIcon name="account_circle" className="text-4xl mb-sm opacity-50" />
          <p>Chưa có tài khoản nào. Hãy thêm tài khoản mới để bắt đầu.</p>
        </div>
      )}

      {/* Edit Account Modal */}
      {editingAccount && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs">
          <div className="bg-surface-container-lowest border border-outline-variant rounded-2xl p-lg w-[400px] shadow-xl flex flex-col gap-md">
            <div className="flex items-center justify-between border-b pb-sm">
              <h3 className="text-title-md font-semibold text-on-surface">Chỉnh sửa tài khoản</h3>
              <button 
                onClick={() => setEditingAccount(null)}
                className="text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-surface-container-low transition"
              >
                <MaterialIcon name="close" />
              </button>
            </div>
            
            <div className="flex flex-col gap-sm">
              <label className="text-xs font-semibold text-on-surface-variant">Tên tài khoản</label>
              <input
                type="text"
                value={editLabel}
                onChange={(e) => setEditLabel(e.target.value)}
                className="border-outline-variant bg-surface rounded-lg border px-md py-sm text-body-sm focus:border-primary focus:outline-none"
                placeholder="Tên tài khoản (vd: Việt, Nam...)"
              />
            </div>
            
            <div className="flex flex-col gap-sm">
              <label className="text-xs font-semibold text-on-surface-variant">Số điện thoại</label>
              <input
                type="text"
                value={editPhone}
                onChange={(e) => setEditPhone(e.target.value)}
                className="border-outline-variant bg-surface rounded-lg border px-md py-sm text-body-sm focus:border-primary focus:outline-none"
                placeholder="Số điện thoại"
              />
            </div>
            
            <div className="flex justify-end gap-sm mt-md border-t pt-sm">
              <button
                type="button"
                onClick={() => setEditingAccount(null)}
                className="border border-outline-variant bg-surface text-on-surface px-md py-sm rounded-lg text-body-sm font-semibold hover:bg-surface-container-low transition"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={isSavingEdit || !editLabel.trim()}
                onClick={async () => {
                  setIsSavingEdit(true);
                  try {
                    await flow.updateAccount(editingAccount.account_id, editLabel, editPhone);
                    setEditingAccount(null);
                  } catch (e) {
                    console.error(e);
                  } finally {
                    setIsSavingEdit(false);
                  }
                }}
                className="bg-primary text-on-primary px-md py-sm rounded-lg text-body-sm font-semibold hover:opacity-90 transition disabled:opacity-50"
              >
                {isSavingEdit ? "Đang lưu..." : "Lưu lại"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
