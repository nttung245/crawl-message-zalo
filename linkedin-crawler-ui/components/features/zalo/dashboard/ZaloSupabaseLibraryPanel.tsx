"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";

import { MaterialIcon } from "@/components/ui";
import {
  bulkDeleteZaloLibraryMessages,
  createZaloLibraryMessage,
  deleteZaloLibraryMessage,
  getZaloLibraryMessages,
  updateZaloLibraryMessage,
} from "@/services/zaloCrawlerService";
import type {
  ZaloLibraryContentKind,
  ZaloLibraryGroupSummary,
  ZaloLibraryMessage,
  ZaloLibraryMessageCreateRequest,
} from "@/types/zalo-api";

interface ZaloSupabaseLibraryPanelProps {
  userId: string;
  selectedMessageIds: string[];
  onSelectedMessageIdsChange: (ids: string[]) => void;
  onMessagesLoaded: (messages: ZaloLibraryMessage[]) => void;
}

const PAGE_SIZE = 20;
const AUTO_REFRESH_INTERVAL_MS = 5000;
const emptyDraft: ZaloLibraryMessageCreateRequest = {
  group_name: "",
  sender_name: "",
  type: "text",
  content: "",
  asset_urls: [],
};

function uploadedAssets(message: ZaloLibraryMessage) {
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

function failedAssetCount(message: ZaloLibraryMessage) {
  return (message.assets || []).filter((asset) => asset.status === "failed").length;
}

function buildGroupSummariesFromMessages(messages: ZaloLibraryMessage[]): ZaloLibraryGroupSummary[] {
  const groupsByName = new Map<string, ZaloLibraryGroupSummary>();
  for (const message of messages) {
    const groupName = message.group_name?.trim();
    if (!groupName) continue;
    const key = groupName.toLowerCase();
    const current =
      groupsByName.get(key) ??
      ({
        group_name: groupName,
        sheet_tab: groupName,
        message_count: 0,
        image_count: 0,
        latest_message_at: null,
      } satisfies ZaloLibraryGroupSummary);
    current.message_count += 1;
    current.image_count += uploadedAssets(message).length;
    if (!current.latest_message_at) {
      current.latest_message_at = message.timestamp_text ?? message.time_text ?? null;
    }
    groupsByName.set(key, current);
  }
  return Array.from(groupsByName.values());
}

function formatGroupTime(value?: string | null) {
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

export function ZaloSupabaseLibraryPanel({
  userId,
  selectedMessageIds,
  onSelectedMessageIdsChange,
  onMessagesLoaded,
}: ZaloSupabaseLibraryPanelProps) {
  const [messages, setMessages] = useState<ZaloLibraryMessage[]>([]);
  const [messageCache, setMessageCache] = useState<Record<string, ZaloLibraryMessage>>({});
  const [groups, setGroups] = useState<ZaloLibraryGroupSummary[]>([]);
  const [selectedGroupName, setSelectedGroupName] = useState("");
  const [groupSearch, setGroupSearch] = useState("");
  const [contentKind, setContentKind] = useState<ZaloLibraryContentKind>("all");
  const [draft, setDraft] = useState<ZaloLibraryMessageCreateRequest>(emptyDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  const selectedSet = useMemo(() => new Set(selectedMessageIds), [selectedMessageIds]);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageMessageIds = messages.map((message) => message.id);
  const isPageSelected = pageMessageIds.length > 0 && pageMessageIds.every((id) => selectedSet.has(id));

  const filteredGroups = useMemo(() => {
    const keyword = groupSearch.trim().toLowerCase();
    if (!keyword) return groups;
    return groups.filter((group) => group.group_name.toLowerCase().includes(keyword));
  }, [groupSearch, groups]);

  const allGroupTotal = useMemo(
    () => groups.reduce((sum, group) => sum + group.message_count, 0),
    [groups],
  );

  const loadMessages = useCallback(async (options?: { silent?: boolean }) => {
    const silent = Boolean(options?.silent);
    if (!silent) {
      setIsLoading(true);
    }
    setError(null);
    try {
      const offset = (page - 1) * PAGE_SIZE;
      const response = await getZaloLibraryMessages(
        userId,
        selectedGroupName || undefined,
        PAGE_SIZE,
        offset,
        contentKind,
      );
      const responseMessages = response.messages ?? [];
      const responseGroups = response.groups?.length
        ? response.groups
        : buildGroupSummariesFromMessages(responseMessages);
      setMessages(responseMessages);
      setGroups(responseGroups);
      setTotal(response.total ?? responseMessages.length);
      setHasMore(Boolean(response.has_more));
      setMessageCache((current) => {
        const next = { ...current };
        for (const message of responseMessages) {
          next[message.id] = message;
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tải thư viện tin nhắn.");
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  }, [contentKind, page, selectedGroupName, userId]);

  useEffect(() => {
    onMessagesLoaded(Object.values(messageCache));
  }, [messageCache, onMessagesLoaded]);

  useEffect(() => {
    setMessages([]);
    setMessageCache({});
    onSelectedMessageIdsChange([]);
    setSelectedGroupName("");
    setGroupSearch("");
    setPage(1);
  }, [onSelectedMessageIdsChange, userId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadMessages();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadMessages]);

  useEffect(() => {
    if (!userId || userId === "default") return;

    const timer = window.setInterval(() => {
      void loadMessages({ silent: true });
    }, AUTO_REFRESH_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [loadMessages, userId]);

  function selectGroup(groupName: string) {
    setSelectedGroupName(groupName);
    setDraft((current) => ({ ...current, group_name: groupName || current.group_name }));
    setPage(1);
  }

  function setMode(nextKind: ZaloLibraryContentKind) {
    setContentKind(nextKind);
    setPage(1);
  }

  function toggleSelected(id: string) {
    if (selectedSet.has(id)) {
      onSelectedMessageIdsChange(selectedMessageIds.filter((item) => item !== id));
      return;
    }
    onSelectedMessageIdsChange([...selectedMessageIds, id]);
  }

  function togglePageSelected() {
    if (isPageSelected) {
      onSelectedMessageIdsChange(selectedMessageIds.filter((id) => !pageMessageIds.includes(id)));
      return;
    }
    onSelectedMessageIdsChange(Array.from(new Set([...selectedMessageIds, ...pageMessageIds])));
  }

  async function handleCreate() {
    const content = draft.content?.trim();
    const assetUrls = draft.asset_urls?.filter((url) => url.trim()) ?? [];
    if (!content && assetUrls.length === 0) {
      setError("Nhập text hoặc URL ảnh trước khi thêm tin.");
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      await createZaloLibraryMessage(userId, {
        ...draft,
        group_name: draft.group_name?.trim() || selectedGroupName || undefined,
        content,
        asset_urls: assetUrls,
      });
      setDraft({ ...emptyDraft, group_name: selectedGroupName });
      await loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể thêm tin nhắn.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSaveEdit(message: ZaloLibraryMessage) {
    setIsSaving(true);
    setError(null);
    try {
      await updateZaloLibraryMessage(userId, message.id, { content: editContent });
      setEditingId(null);
      await loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể sửa tin nhắn.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete(messageId: string) {
    setIsSaving(true);
    setError(null);
    try {
      await deleteZaloLibraryMessage(userId, messageId);
      onSelectedMessageIdsChange(selectedMessageIds.filter((id) => id !== messageId));
      setMessageCache((current) => {
        const next = { ...current };
        delete next[messageId];
        return next;
      });
      await loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể xóa tin nhắn.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleBulkDeleteSelected() {
    if (selectedMessageIds.length === 0) return;
    if (!window.confirm(`Xóa ${selectedMessageIds.length} tin đã chọn?`)) return;
    setIsSaving(true);
    setError(null);
    try {
      await bulkDeleteZaloLibraryMessages(userId, { message_ids: selectedMessageIds });
      setMessageCache((current) => {
        const next = { ...current };
        for (const id of selectedMessageIds) {
          delete next[id];
        }
        return next;
      });
      onSelectedMessageIdsChange([]);
      await loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể xóa hàng loạt.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeleteAllMatching() {
    const scope = selectedGroupName.trim()
      ? `toàn bộ tin trong nhóm "${selectedGroupName.trim()}"`
      : "toàn bộ thư viện";
    if (!window.confirm(`Xóa ${scope}? Hành động này là xóa mềm trong Supabase.`)) return;
    setIsSaving(true);
    setError(null);
    try {
      await bulkDeleteZaloLibraryMessages(userId, {
        group_name: selectedGroupName.trim() || undefined,
        delete_all_matching: true,
      });
      onSelectedMessageIdsChange([]);
      setMessageCache({});
      await loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể xóa tất cả.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="border-outline-variant bg-surface-container-lowest rounded-2xl border p-lg shadow-sm">
      <div className="mb-lg flex flex-col gap-md lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-h2 font-semibold text-on-surface">Thư viện tin nhắn</h2>
          <p className="text-body-sm text-on-surface-variant">
            Tin đã crawl được lưu trong Supabase theo từng group. Chọn tin ở đây để đưa sang chiến dịch gửi.
          </p>
        </div>
        <div className="flex flex-col gap-sm sm:flex-row">
          <div className="border-outline-variant bg-surface inline-flex rounded-xl border p-1">
            {(["all", "text", "image"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setMode(mode)}
                className={`rounded-lg px-md py-xs text-body-sm font-semibold ${
                  contentKind === mode
                    ? "bg-primary text-on-primary"
                    : "text-on-surface-variant hover:bg-surface-container"
                }`}
              >
                {mode === "all" ? "Tất cả" : mode === "text" ? "Text" : "Ảnh"}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => void loadMessages()}
            disabled={isLoading}
            className="bg-primary text-on-primary inline-flex items-center justify-center gap-sm rounded-xl px-md py-sm text-body-sm font-semibold disabled:opacity-60"
          >
            <MaterialIcon name="refresh" className="text-base" />
            Tải lại
          </button>
        </div>
      </div>

      {error ? (
        <div className="border-error-container bg-error-container/40 text-error mb-md rounded-xl border px-md py-sm text-body-sm">
          {error}
        </div>
      ) : null}

      <div className="grid gap-lg xl:grid-cols-[300px_1fr]">
        <aside className="border-outline-variant bg-surface rounded-xl border p-md">
          <div className="mb-md">
            <label className="text-label-sm font-semibold uppercase tracking-wide text-on-surface-variant">
              Group đã crawl
            </label>
            <input
              value={groupSearch}
              onChange={(event) => setGroupSearch(event.target.value)}
              placeholder="Tìm group"
              className="border-outline-variant mt-sm w-full rounded-lg border px-md py-sm text-body-sm"
            />
          </div>
          <div className="flex max-h-[520px] flex-col gap-sm overflow-y-auto pr-xs">
            <button
              type="button"
              onClick={() => selectGroup("")}
              className={`rounded-lg border px-md py-sm text-left text-body-sm ${
                selectedGroupName === ""
                  ? "border-primary bg-primary-container text-on-primary-container"
                  : "border-outline-variant bg-surface"
              }`}
            >
              <span className="block font-semibold">Tất cả group</span>
              <span className="text-on-surface-variant">{allGroupTotal} tin</span>
            </button>
            {filteredGroups.map((group) => (
              <button
                key={group.group_name}
                type="button"
                onClick={() => selectGroup(group.group_name)}
                className={`rounded-lg border px-md py-sm text-left text-body-sm ${
                  selectedGroupName === group.group_name
                    ? "border-primary bg-primary-container text-on-primary-container"
                    : "border-outline-variant bg-surface"
                }`}
              >
                <span className="line-clamp-2 block font-semibold">{group.group_name}</span>
                <span className="text-on-surface-variant">
                  {group.message_count} tin · {group.image_count} ảnh
                </span>
                <span className="text-on-surface-variant block text-xs">
                  Mới nhất: {formatGroupTime(group.latest_message_at)}
                </span>
              </button>
            ))}
            {filteredGroups.length === 0 ? (
              <div className="border-outline-variant rounded-lg border px-md py-lg text-body-sm text-on-surface-variant">
                Chưa có group phù hợp.
              </div>
            ) : null}
          </div>
        </aside>

        <div>
          <div className="border-outline-variant bg-surface mb-lg grid gap-md rounded-xl border p-md lg:grid-cols-[1fr_1fr_auto]">
            <input
              value={draft.group_name ?? ""}
              onChange={(event) => setDraft((current) => ({ ...current, group_name: event.target.value }))}
              placeholder="Nhóm nguồn"
              className="border-outline-variant rounded-lg border px-md py-sm text-body-sm"
            />
            <input
              value={(draft.asset_urls ?? []).join("\n")}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  asset_urls: event.target.value.split("\n").map((value) => value.trim()),
                }))
              }
              placeholder="URL ảnh, mỗi dòng một ảnh"
              className="border-outline-variant rounded-lg border px-md py-sm text-body-sm"
            />
            <button
              type="button"
              onClick={() => void handleCreate()}
              disabled={isSaving}
              className="bg-secondary-container text-on-secondary-container inline-flex items-center justify-center gap-sm rounded-xl px-md py-sm text-body-sm font-semibold disabled:opacity-60"
            >
              <MaterialIcon name="add" className="text-base" />
              Thêm
            </button>
            <textarea
              value={draft.content ?? ""}
              onChange={(event) => setDraft((current) => ({ ...current, content: event.target.value }))}
              placeholder="Nội dung tin nhắn"
              rows={3}
              className="border-outline-variant rounded-lg border px-md py-sm text-body-sm lg:col-span-3"
            />
          </div>

          <div className="mb-md flex flex-wrap items-center justify-between gap-sm">
            <label className="inline-flex items-center gap-2 text-body-sm font-semibold text-on-surface">
              <input
                type="checkbox"
                checked={isPageSelected}
                onChange={togglePageSelected}
                disabled={messages.length === 0}
              />
              Chọn trang này
            </label>
            <div className="flex flex-wrap gap-sm">
              <button
                type="button"
                onClick={() => void handleBulkDeleteSelected()}
                disabled={selectedMessageIds.length === 0 || isSaving}
                className="border-error-container text-error inline-flex items-center gap-1 rounded-lg border px-sm py-xs text-body-sm font-semibold disabled:opacity-60"
              >
                <MaterialIcon name="delete" className="text-base" />
                Xóa đã chọn ({selectedMessageIds.length})
              </button>
              <button
                type="button"
                onClick={() => void handleDeleteAllMatching()}
                disabled={total === 0 || isSaving}
                className="border-error-container text-error inline-flex items-center gap-1 rounded-lg border px-sm py-xs text-body-sm font-semibold disabled:opacity-60"
              >
                <MaterialIcon name="delete" className="text-base" />
                {selectedGroupName ? "Xóa group này" : "Xóa tất cả"}
              </button>
            </div>
          </div>

          <div className="mb-md flex flex-wrap items-center justify-between gap-sm text-body-sm text-on-surface-variant">
            <span>
              Hiển thị {messages.length} / {total} tin
              {selectedGroupName ? ` trong ${selectedGroupName}` : ""}
              {hasMore ? "" : ""}
            </span>
            <div className="flex items-center gap-sm">
              <button
                type="button"
                className="border-outline-variant rounded-lg border px-sm py-xs font-semibold disabled:opacity-50"
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                disabled={currentPage <= 1 || isLoading}
              >
                Trước
              </button>
              <span>
                Trang {currentPage}/{totalPages}
              </span>
              <button
                type="button"
                className="border-outline-variant rounded-lg border px-sm py-xs font-semibold disabled:opacity-50"
                onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                disabled={currentPage >= totalPages || isLoading}
              >
                Sau
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-md">
            {messages.length === 0 ? (
              <div className="border-outline-variant bg-surface rounded-xl border px-md py-lg text-body-sm text-on-surface-variant">
                {isLoading ? "Đang tải thư viện..." : "Chưa có tin nhắn phù hợp trong Supabase."}
              </div>
            ) : null}

            {messages.map((message) => {
              const isSelected = selectedSet.has(message.id);
              const assets = uploadedAssets(message);
              const failedAssets = failedAssetCount(message);
              const isEditing = editingId === message.id;
              return (
                <article
                  key={message.id}
                  className={`border-outline-variant bg-surface rounded-xl border p-md shadow-sm ${
                    isSelected ? "ring-primary ring-2" : ""
                  }`}
                >
                  <div className="mb-sm flex flex-col gap-sm sm:flex-row sm:items-start sm:justify-between">
                    <label className="flex items-start gap-sm">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelected(message.id)}
                        className="mt-1 h-4 w-4"
                      />
                      <span>
                        <span className="block text-body-sm font-semibold text-on-surface">
                          {message.group_name || "Không rõ nhóm"}
                        </span>
                        <span className="text-body-sm text-on-surface-variant">
                          {message.sender_name || "Không rõ người gửi"} ·{" "}
                          {formatGroupTime(message.time_text || message.timestamp_text)}
                        </span>
                        <span className="mt-xs flex flex-wrap gap-xs">
                          {assets.length > 0 ? (
                            <span className="rounded-full bg-secondary-container px-sm py-0.5 text-xs font-semibold text-on-secondary-container">
                              {assets.length} ảnh gửi được
                            </span>
                          ) : null}
                          {failedAssets > 0 ? (
                            <span className="rounded-full bg-error-container px-sm py-0.5 text-xs font-semibold text-error">
                              {failedAssets} ảnh lỗi upload
                            </span>
                          ) : null}
                        </span>
                      </span>
                    </label>
                    <div className="flex gap-sm">
                      <button
                        type="button"
                        onClick={() => {
                          setEditingId(message.id);
                          setEditContent(message.content ?? "");
                        }}
                        className="border-outline-variant inline-flex items-center gap-1 rounded-lg border px-sm py-xs text-body-sm font-semibold"
                      >
                        <MaterialIcon name="edit" className="text-base" />
                        Sửa
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDelete(message.id)}
                        disabled={isSaving}
                        className="border-error-container text-error inline-flex items-center gap-1 rounded-lg border px-sm py-xs text-body-sm font-semibold disabled:opacity-60"
                      >
                        <MaterialIcon name="delete" className="text-base" />
                        Xóa
                      </button>
                    </div>
                  </div>

                  {isEditing ? (
                    <div className="flex flex-col gap-sm">
                      <textarea
                        value={editContent}
                        onChange={(event) => setEditContent(event.target.value)}
                        rows={4}
                        className="border-outline-variant rounded-lg border px-md py-sm text-body-sm"
                      />
                      <div className="flex gap-sm">
                        <button
                          type="button"
                          onClick={() => void handleSaveEdit(message)}
                          disabled={isSaving}
                          className="bg-primary text-on-primary rounded-lg px-md py-sm text-body-sm font-semibold disabled:opacity-60"
                        >
                          Lưu
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="border-outline-variant rounded-lg border px-md py-sm text-body-sm font-semibold"
                        >
                          Hủy
                        </button>
                      </div>
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap text-body-sm text-on-surface">{message.content || ""}</p>
                  )}

                  {assets.length > 0 ? (
                    <div className="mt-md grid gap-sm sm:grid-cols-2 lg:grid-cols-4">
                      {assets.map((asset) => (
                        <a
                          key={asset.id || asset.storage_url}
                          href={asset.storage_url || "#"}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <Image
                            src={asset.storage_url || ""}
                            alt="Ảnh Zalo đã lưu"
                            width={320}
                            height={180}
                            unoptimized
                            className="border-outline-variant aspect-video w-full rounded-lg border object-cover"
                          />
                        </a>
                      ))}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
