"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MaterialIcon } from "@/components/ui";
import type { ZaloCrawlerFlowValue } from "@/hooks/useZaloCrawlerFlow";
import {
  getZaloConversationMessages,
  getZaloConversations,
  syncZaloRecentConversations,
} from "@/services/zaloCrawlerService";
import type {
  ZaloConversationSummary,
  ZaloLibraryMessage,
  ZaloSyncRecentResponse,
} from "@/types/zalo-api";

const REFRESH_INTERVAL_MS = 2000;
const MESSAGE_PAGE_SIZE = 50;
const SYNC_CONVERSATION_LIMIT = 50;
const SYNC_MESSAGES_PER_CONVERSATION = 50;
const BOTTOM_THRESHOLD_PX = 96;

interface ZaloInboxMonitorPanelProps {
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

function shortId(value: string, head = 10, tail = 6) {
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function isFallbackName(name: string | null | undefined, id: string) {
  const cleanName = String(name || "").trim();
  return !cleanName || cleanName === id || cleanName === `Conversation ${id}`;
}

function conversationTitle(conversation: ZaloConversationSummary | null) {
  if (!conversation) return "Chọn một hội thoại";
  if (isFallbackName(conversation.conversation_name, conversation.conversation_id)) {
    return "Hội thoại chưa đặt tên";
  }
  return conversation.conversation_name;
}

function initials(value: string) {
  const words = value
    .replace(/^\[|\]$/g, "")
    .split(/\s+/)
    .filter(Boolean);
  const first = words[0]?.[0] ?? "Z";
  const second = words.length > 1 ? words[words.length - 1]?.[0] : "";
  return `${first}${second}`.toUpperCase();
}

function messageKey(message: ZaloLibraryMessage) {
  return message.id || message.source_message_id || `${message.group_id}-${message.timestamp_text}-${message.content}`;
}

function isNearBottom(element: HTMLDivElement | null) {
  if (!element) return true;
  return element.scrollHeight - element.scrollTop - element.clientHeight <= BOTTOM_THRESHOLD_PX;
}

function accountStatus(account: ZaloCrawlerFlowValue["accounts"][number]) {
  if (account.listener?.connected) return { text: "Listener online", tone: "success" as const };
  if (account.listener?.running) return { text: "Listener đang chạy", tone: "warning" as const };
  if (account.has_auth) return { text: "Đã đăng nhập", tone: "success" as const };
  return { text: "Chưa đăng nhập", tone: "muted" as const };
}

function messageAssets(message: ZaloLibraryMessage) {
  const list = (message.assets || []).filter((asset) => asset.status === "uploaded" && asset.storage_url);
  const seen = new Set<string>();
  const deduped: typeof list = [];
  for (const asset of list) {
    const src = asset.source_url || "";
    const filename = src.split("/").pop()?.split("?")[0] || src;
    if (filename && seen.has(filename)) {
      continue;
    }
    if (filename) {
      seen.add(filename);
    }
    deduped.push(asset);
  }
  return deduped;
}

function StatusDot({ tone }: { tone: "success" | "warning" | "muted" }) {
  const className =
    tone === "success"
      ? "bg-green-500"
      : tone === "warning"
        ? "bg-amber-500"
        : "bg-on-surface-variant/50";
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${className}`} />;
}

export function ZaloInboxMonitorPanel({ flow }: ZaloInboxMonitorPanelProps) {
  const [newAccountLabel, setNewAccountLabel] = useState("");
  const [newAccountPhone, setNewAccountPhone] = useState("");
  const [conversations, setConversations] = useState<ZaloConversationSummary[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ZaloLibraryMessage[]>([]);
  const [messageTotal, setMessageTotal] = useState(0);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const [newMessageCount, setNewMessageCount] = useState(0);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isLoadingOlderMessages, setIsLoadingOlderMessages] = useState(false);
  const [isSyncingRecent, setIsSyncingRecent] = useState(false);
  const [conversationError, setConversationError] = useState<string | null>(null);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [syncSummary, setSyncSummary] = useState<ZaloSyncRecentResponse | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [avatarErrors, setAvatarErrors] = useState<Record<string, boolean>>({});
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const pendingScrollRef = useRef<"bottom" | "preserve" | null>(null);
  const preservedScrollRef = useRef<{ previousHeight: number; previousTop: number }>({ previousHeight: 0, previousTop: 0 });

  const selectedAccount = useMemo(
    () => flow.accounts.find((account) => account.account_id === flow.userId) ?? null,
    [flow.accounts, flow.userId],
  );
  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.conversation_id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );

  const loadConversations = useCallback(async (options?: { silent?: boolean }) => {
    if (!flow.userId || flow.userId === "default") {
      setConversations([]);
      setSelectedConversationId(null);
      return;
    }
    if (!options?.silent) setIsLoadingConversations(true);
    setConversationError(null);
    try {
      const response = await getZaloConversations(flow.userId);
      const nextConversations = response.conversations ?? [];
      setConversations(nextConversations);
      setSelectedConversationId((current) => {
        if (current && nextConversations.some((item) => item.conversation_id === current)) {
          return current;
        }
        return nextConversations[0]?.conversation_id ?? null;
      });
    } catch (error) {
      setConversationError(error instanceof Error ? error.message : "Không thể tải danh sách hội thoại.");
    } finally {
      if (!options?.silent) setIsLoadingConversations(false);
    }
  }, [flow.userId]);

  const loadLatestMessages = useCallback(async (conversationId: string | null, options?: { silent?: boolean }) => {
    if (!flow.userId || flow.userId === "default" || !conversationId) {
      setMessages([]);
      setMessageTotal(0);
      setHasOlderMessages(false);
      return;
    }
    if (!options?.silent) setIsLoadingMessages(true);
    setMessageError(null);
    try {
      const response = await getZaloConversationMessages(
        flow.userId,
        conversationId,
        MESSAGE_PAGE_SIZE,
        0,
      );
      pendingScrollRef.current = "bottom";
      setMessages(response.messages ?? []);
      setMessageTotal(response.total ?? 0);
      setHasOlderMessages(Boolean(response.has_more));
      setNewMessageCount(0);
    } catch (error) {
      setMessageError(error instanceof Error ? error.message : "Không thể tải tin nhắn hội thoại.");
    } finally {
      if (!options?.silent) setIsLoadingMessages(false);
    }
  }, [flow.userId]);

  const pollLatestMessages = useCallback(async (conversationId: string | null) => {
    if (!flow.userId || flow.userId === "default" || !conversationId) return;
    const shouldStickToBottom = isNearBottom(messageListRef.current);
    try {
      const response = await getZaloConversationMessages(
        flow.userId,
        conversationId,
        MESSAGE_PAGE_SIZE,
        0,
      );
      const latestMessages = response.messages ?? [];
      setMessageTotal(response.total ?? 0);
      setHasOlderMessages((response.total ?? 0) > messages.length);
      setMessages((current) => {
        const latestMap = new Map(latestMessages.map(m => [messageKey(m), m]));
        
        // Update existing messages
        const updated = current.map(m => {
          const key = messageKey(m);
          if (latestMap.has(key)) {
            return latestMap.get(key)!;
          }
          return m;
        });
        
        // Find messages in latestMessages that are not in current
        const existingKeys = new Set(current.map(messageKey));
        const newMessages = latestMessages.filter(m => !existingKeys.has(messageKey(m)));
        
        if (newMessages.length === 0) {
          const hasChanges = current.some((m, idx) => {
            const key = messageKey(m);
            if (!latestMap.has(key)) return false;
            const next = latestMap.get(key)!;
            return JSON.stringify(m) !== JSON.stringify(next);
          });
          return hasChanges ? updated : current;
        }
        
        if (!shouldStickToBottom) setNewMessageCount((count) => count + newMessages.length);
        if (shouldStickToBottom) pendingScrollRef.current = "bottom";
        
        return [...updated, ...newMessages];
      });
    } catch {
      // Silent polling should not interrupt the operator while they are reading.
    }
  }, [flow.userId, messages.length]);

  const loadOlderMessages = useCallback(async () => {
    if (!flow.userId || !selectedConversationId || isLoadingOlderMessages || !hasOlderMessages) return;
    const element = messageListRef.current;
    const previousHeight = element?.scrollHeight ?? 0;
    const previousTop = element?.scrollTop ?? 0;
    setIsLoadingOlderMessages(true);
    setMessageError(null);
    try {
      const response = await getZaloConversationMessages(
        flow.userId,
        selectedConversationId,
        MESSAGE_PAGE_SIZE,
        messages.length,
      );
      const olderMessages = response.messages ?? [];
      preservedScrollRef.current = { previousHeight, previousTop };
      pendingScrollRef.current = "preserve";
      setMessages((current) => {
        const existing = new Set(current.map(messageKey));
        const uniqueOlder = olderMessages.filter((message) => !existing.has(messageKey(message)));
        return [...uniqueOlder, ...current];
      });
      setMessageTotal(response.total ?? messageTotal);
      setHasOlderMessages(messages.length + olderMessages.length < (response.total ?? 0));
    } catch (error) {
      setMessageError(error instanceof Error ? error.message : "Không thể tải tin nhắn cũ hơn.");
    } finally {
      setIsLoadingOlderMessages(false);
    }
  }, [flow.userId, hasOlderMessages, isLoadingOlderMessages, messageTotal, messages.length, selectedConversationId]);

  const scrollToLatest = useCallback(() => {
    const element = messageListRef.current;
    if (element) element.scrollTop = element.scrollHeight;
    setNewMessageCount(0);
  }, []);

  const syncRecentConversations = useCallback(async () => {
    if (!flow.userId || flow.userId === "default" || isSyncingRecent) return;
    setIsSyncingRecent(true);
    setSyncError(null);
    setSyncSummary(null);
    try {
      const response = await syncZaloRecentConversations(
        flow.userId,
        SYNC_CONVERSATION_LIMIT,
        SYNC_MESSAGES_PER_CONVERSATION,
      );
      setSyncSummary(response);
      await loadConversations();
      if (selectedConversationId) await loadLatestMessages(selectedConversationId, { silent: true });
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : "Không thể đồng bộ hội thoại gần đây.");
    } finally {
      setIsSyncingRecent(false);
    }
  }, [flow.userId, isSyncingRecent, loadConversations, loadLatestMessages, selectedConversationId]);

  // Scroll after React has committed new messages to the DOM
  useEffect(() => {
    const action = pendingScrollRef.current;
    if (!action) return;
    pendingScrollRef.current = null;
    const element = messageListRef.current;
    if (!element) return;
    if (action === "bottom") {
      element.scrollTop = element.scrollHeight;
    } else if (action === "preserve") {
      const { previousHeight, previousTop } = preservedScrollRef.current;
      element.scrollTop = element.scrollHeight - previousHeight + previousTop;
    }
  }, [messages]);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    setMessages([]);
    setMessageTotal(0);
    setHasOlderMessages(false);
    setNewMessageCount(0);
    void loadLatestMessages(selectedConversationId);
  }, [loadLatestMessages, selectedConversationId]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadConversations({ silent: true });
      void pollLatestMessages(selectedConversationId);
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loadConversations, pollLatestMessages, selectedConversationId]);

  async function handleCreateAccount() {
    const label = newAccountLabel.trim();
    if (!label) return;
    await flow.createAccount(label, newAccountPhone.trim() || undefined);
    setNewAccountLabel("");
    setNewAccountPhone("");
  }

  const accountCount = flow.accounts.length;
  const selectedStatus = selectedAccount ? accountStatus(selectedAccount) : null;

  return (
    <div className="grid min-h-[72vh] gap-md xl:grid-cols-[300px_380px_minmax(0,1fr)]">
      <section className="border-outline-variant bg-surface-container-lowest flex min-h-0 flex-col rounded-lg border shadow-sm">
        <header className="border-outline-variant flex items-start justify-between gap-sm border-b p-md">
          <div>
            <h2 className="text-title-lg font-semibold text-on-surface">Tài khoản Zalo</h2>
            <p className="text-body-sm text-on-surface-variant">Mỗi tài khoản có listener riêng.</p>
          </div>
          <span className="rounded-full bg-surface-container-high px-sm py-xs text-xs font-semibold text-on-surface-variant">
            {accountCount}
          </span>
        </header>

        <div className="border-outline-variant grid gap-xs border-b p-md">
          <input
            value={newAccountLabel}
            onChange={(event) => setNewAccountLabel(event.target.value)}
            placeholder="Tên tài khoản"
            className="border-outline-variant bg-surface min-h-10 rounded-md border px-md py-sm text-body-sm"
          />
          <input
            value={newAccountPhone}
            onChange={(event) => setNewAccountPhone(event.target.value)}
            placeholder="Số điện thoại nếu cần"
            className="border-outline-variant bg-surface min-h-10 rounded-md border px-md py-sm text-body-sm"
          />
          <button
            type="button"
            onClick={() => void handleCreateAccount()}
            disabled={!newAccountLabel.trim()}
            className="bg-primary text-on-primary inline-flex min-h-10 items-center justify-center gap-sm rounded-md px-md py-sm text-body-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
          >
            <MaterialIcon name="add" className="text-base" />
            Thêm tài khoản
          </button>
        </div>

        {flow.accountsError ? (
          <div className="border-error-container bg-error-container/40 text-error m-md rounded-md border px-md py-sm text-body-sm">
            {flow.accountsError}
          </div>
        ) : null}

        <div className="min-h-0 flex-1 space-y-xs overflow-y-auto p-md">
          {flow.accounts.map((account) => {
            const active = account.account_id === flow.userId;
            const status = accountStatus(account);
            return (
              <button
                key={account.account_id}
                type="button"
                onClick={() => flow.switchAccount(account.account_id)}
                className={`w-full rounded-lg border p-md text-left transition ${
                  active
                    ? "border-primary bg-primary text-on-primary"
                    : "border-outline-variant bg-surface hover:bg-surface-container-low"
                }`}
              >
                <div className="mb-xs flex items-start justify-between gap-sm">
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{account.label || "Tài khoản Zalo"}</div>
                    <div className="truncate text-body-sm opacity-80">{shortId(account.account_id)}</div>
                  </div>
                  {active ? <MaterialIcon name="check_circle" className="text-base" filled /> : null}
                </div>
                <div className="flex items-center gap-xs text-body-sm opacity-85">
                  <StatusDot tone={status.tone} />
                  <span>{status.text}</span>
                </div>
                <div className="mt-xs text-body-sm opacity-80">Tin đã nhận: {account.listener?.messages_seen ?? 0}</div>
              </button>
            );
          })}
          {flow.accounts.length === 0 && !flow.isLoadingAccounts ? (
            <div className="border-outline-variant rounded-lg border px-md py-lg text-body-sm text-on-surface-variant">
              Chưa có tài khoản nào. Tạo tài khoản rồi đăng nhập QR để bắt đầu monitor.
            </div>
          ) : null}
        </div>
      </section>

      <section className="border-outline-variant bg-surface-container-lowest flex min-h-0 flex-col rounded-lg border shadow-sm">
        <header className="border-outline-variant border-b p-md">
          <div className="flex items-start justify-between gap-sm">
            <div>
              <h2 className="text-title-lg font-semibold text-on-surface">Hội thoại</h2>
              <p className="text-body-sm text-on-surface-variant">Tự cập nhật mỗi 5 giây.</p>
            </div>
            <div className="flex gap-xs">
              <button
                type="button"
                onClick={() => void syncRecentConversations()}
                disabled={!selectedAccount?.has_auth || isSyncingRecent}
                className="border-outline-variant bg-surface inline-flex h-9 w-9 items-center justify-center rounded-md border disabled:opacity-50"
                title="Đồng bộ 50 hội thoại mới nhất"
              >
                <MaterialIcon name="sync" className="text-base" />
              </button>
              <button
                type="button"
                onClick={() => void loadConversations()}
                className="border-outline-variant bg-surface inline-flex h-9 w-9 items-center justify-center rounded-md border"
                title="Làm mới"
              >
                <MaterialIcon name="refresh" className="text-base" />
              </button>
            </div>
          </div>
        </header>

        <div className="border-outline-variant border-b p-md">
          {!selectedAccount ? (
            <div className="border-outline-variant bg-surface rounded-lg border px-md py-lg text-body-sm text-on-surface-variant">
              Chọn hoặc tạo một tài khoản Zalo để xem hội thoại.
            </div>
          ) : (
            <div className="rounded-lg border border-outline-variant bg-surface p-md">
              <div className="mb-xs text-label-md font-semibold uppercase text-on-surface-variant">Trạng thái</div>
              <div className="flex items-center justify-between gap-md">
                <div>
                  <div className="font-semibold text-on-surface">
                    {flow.isCheckingLoginStatus ? "Đang kiểm tra" : flow.isLoggedIn ? "Đã đăng nhập" : "Chưa đăng nhập"}
                  </div>
                  <div className="mt-xs flex items-center gap-xs text-body-sm text-on-surface-variant">
                    {selectedStatus ? <StatusDot tone={selectedStatus.tone} /> : null}
                    <span>{selectedStatus?.text ?? "Chưa rõ trạng thái"}</span>
                  </div>
                </div>
                <div className="flex shrink-0 gap-xs">
                  {!flow.isLoggedIn ? (
                    <button
                      type="button"
                      onClick={() => void flow.startSession()}
                      disabled={flow.isStartingSession}
                      className="bg-primary text-on-primary rounded-md px-md py-xs text-xs font-bold uppercase disabled:opacity-60"
                    >
                      {flow.isStartingSession ? "Đang tạo QR" : "Đăng nhập"}
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => void flow.endSession()}
                      disabled={flow.isEndingSession}
                      className="rounded-md border border-red-300 bg-red-50 px-md py-xs text-xs font-bold uppercase text-red-700 disabled:opacity-60"
                    >
                      {flow.isEndingSession ? "Đang đóng" : "Kết thúc"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {isSyncingRecent ? (
            <div className="mt-sm rounded-md border border-blue-200 bg-blue-50 px-md py-sm text-body-sm text-blue-800">
              Đang đồng bộ tối đa 50 hội thoại mới nhất, mỗi hội thoại tối đa 50 tin...
            </div>
          ) : null}
          {syncSummary ? (
            <div className="mt-sm rounded-md border border-green-200 bg-green-50 px-md py-sm text-body-sm text-green-800">
              Đã quét {syncSummary.scanned}/50, lưu {syncSummary.messages_saved} tin từ {syncSummary.groups_with_messages} hội thoại, lỗi {syncSummary.errors}.
            </div>
          ) : null}
          {syncError ? (
            <div className="mt-sm rounded-md border border-red-200 bg-red-50 px-md py-sm text-body-sm text-red-700">
              {syncError}
            </div>
          ) : null}
        </div>

        {conversationError ? (
          <div className="border-error-container bg-error-container/40 text-error m-md rounded-md border px-md py-sm text-body-sm">
            {conversationError}
          </div>
        ) : null}

        <div className="min-h-0 flex-1 space-y-xs overflow-y-auto p-md">
          {conversations.map((conversation) => {
            const active = conversation.conversation_id === selectedConversationId;
            const title = conversationTitle(conversation);
            const hasMessages = conversation.has_messages !== false;
            return (
              <button
                key={conversation.conversation_id}
                type="button"
                onClick={() => setSelectedConversationId(conversation.conversation_id)}
                className={`w-full rounded-lg border p-md text-left transition ${
                  active
                    ? "border-primary bg-primary text-on-primary"
                    : "border-outline-variant bg-surface hover:bg-surface-container-low"
                }`}
              >
                <div className="flex gap-sm">
                  {conversation.avatar_url && !avatarErrors[conversation.conversation_id] ? (
                    <img
                      src={conversation.avatar_url}
                      alt={title}
                      onError={() => setAvatarErrors((prev) => ({ ...prev, [conversation.conversation_id]: true }))}
                      className="h-10 w-10 shrink-0 rounded-full object-cover border border-outline-variant/30 bg-surface-container-low"
                    />
                  ) : (
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
                        active ? "bg-white/20" : "bg-primary-container text-on-primary-container"
                      }`}
                    >
                      {initials(title)}
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-sm">
                      <div className="min-w-0 truncate font-semibold">{title}</div>
                      <span
                        className={`shrink-0 rounded-full px-sm py-0.5 text-xs font-semibold ${
                          active ? "bg-white/20 text-on-primary" : "bg-surface-container-high text-on-surface"
                        }`}
                      >
                        {conversation.message_count}
                      </span>
                    </div>
                    <div className="truncate text-body-sm opacity-80">
                      {hasMessages
                        ? `${conversation.latest_sender_name ? `${conversation.latest_sender_name}: ` : ""}${conversation.latest_content || "Tin nhắn mới"}`
                        : "Chưa có tin lưu"}
                    </div>
                    <div className="mt-xs flex items-center justify-between gap-sm text-xs opacity-75">
                      <span>{formatTime(conversation.latest_message_at)}</span>
                      {isFallbackName(conversation.conversation_name, conversation.conversation_id) ? (
                        <span>{shortId(conversation.conversation_id, 8, 4)}</span>
                      ) : null}
                    </div>
                  </div>
                </div>
              </button>
            );
          })}
          {conversations.length === 0 && !isLoadingConversations ? (
            <div className="border-outline-variant rounded-lg border px-md py-lg text-body-sm text-on-surface-variant">
              Chưa có hội thoại nào. Bấm đồng bộ để quét 50 group mới nhất từ Zalo.
            </div>
          ) : null}
          {isLoadingConversations ? (
            <div className="px-md py-lg text-body-sm text-on-surface-variant">Đang tải hội thoại...</div>
          ) : null}
        </div>
      </section>

      <section className="border-outline-variant bg-surface-container-lowest flex min-h-0 flex-col rounded-lg border shadow-sm">
        <header className="border-outline-variant flex items-start justify-between gap-sm border-b p-md">
          <div className="min-w-0">
            <h2 className="text-title-lg font-semibold text-on-surface">Tin nhắn</h2>
            <p className="truncate text-body-sm text-on-surface-variant">
              {selectedConversation
                ? `${conversationTitle(selectedConversation)} · ${shortId(selectedConversation.conversation_id)}`
                : "Chọn một hội thoại để xem nội dung."}
            </p>
          </div>
          <span className="rounded-full bg-surface-container-high px-sm py-xs text-xs font-semibold text-on-surface-variant">
            {messages.length}/{messageTotal} tin
          </span>
        </header>

        {messageError ? (
          <div className="border-error-container bg-error-container/40 text-error m-md rounded-md border px-md py-sm text-body-sm">
            {messageError}
          </div>
        ) : null}

        <div
          ref={messageListRef}
          className="relative min-h-0 flex-1 space-y-sm overflow-y-auto overflow-x-hidden bg-surface-container-low p-md"
        >
          {hasOlderMessages ? (
            <div className="sticky top-0 z-10 flex justify-center pb-sm">
              <button
                type="button"
                onClick={() => void loadOlderMessages()}
                disabled={isLoadingOlderMessages}
                className="border-outline-variant bg-surface rounded-full border px-md py-xs text-xs font-semibold shadow-sm disabled:opacity-60"
              >
                {isLoadingOlderMessages ? "Đang tải..." : "Tải tin cũ hơn"}
              </button>
            </div>
          ) : null}

          {messages.map((message) => {
            const assets = messageAssets(message);
            const sender = message.sender_name || (message.is_sent ? "Bạn" : "Khách");
            return (
              <article
                key={messageKey(message)}
                className={`max-w-[78%] rounded-lg px-md py-sm shadow-sm ${
                  message.is_sent
                    ? "ml-auto bg-primary text-on-primary"
                    : "mr-auto border border-outline-variant bg-surface text-on-surface"
                }`}
              >
                <div className="mb-xs flex flex-wrap items-center gap-sm text-xs opacity-80">
                  <span className="font-semibold">{sender}</span>
                  <span>{formatTime(message.timestamp_text || message.time_text)}</span>
                </div>
                {message.content ? <p className="whitespace-pre-wrap break-words text-body-sm">{message.content}</p> : null}
                {assets.length > 0 ? (
                  <div className="mt-sm grid gap-sm sm:grid-cols-2">
                    {assets.map((asset) => (
                      <a
                        key={asset.id || asset.storage_url}
                        href={asset.storage_url || "#"}
                        target="_blank"
                        rel="noreferrer"
                        className="block overflow-hidden rounded-md border border-outline-variant bg-white"
                      >
                        <Image
                          src={asset.storage_url || ""}
                          alt="Ảnh trong tin nhắn Zalo"
                          width={260}
                          height={180}
                          className="h-auto w-full object-cover"
                          unoptimized
                        />
                      </a>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}

          {newMessageCount > 0 ? (
            <div className="sticky bottom-sm z-10 flex justify-center">
              <button
                type="button"
                onClick={scrollToLatest}
                className="bg-primary text-on-primary rounded-full px-md py-xs text-xs font-semibold shadow-md"
              >
                Có {newMessageCount} tin mới
              </button>
            </div>
          ) : null}

          {messages.length === 0 && !isLoadingMessages ? (
            <div className="border-outline-variant bg-surface rounded-lg border px-md py-lg text-body-sm text-on-surface-variant">
              Chưa có tin nhắn trong hội thoại này.
            </div>
          ) : null}
          {isLoadingMessages ? (
            <div className="px-md py-lg text-body-sm text-on-surface-variant">Đang tải tin nhắn...</div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
