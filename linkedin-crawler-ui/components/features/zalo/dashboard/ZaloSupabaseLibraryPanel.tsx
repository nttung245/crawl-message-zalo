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
const emptyDraft: ZaloLibraryMessageCreateRequest = {
  group_name: "",
  sender_name: "",
  type: "text",
  content: "",
  asset_urls: [],
};

function uploadedAssets(message: ZaloLibraryMessage) {
  return (message.assets || []).filter((asset) => asset.status === "uploaded" && asset.storage_url);
}

export function ZaloSupabaseLibraryPanel({
  userId,
  selectedMessageIds,
  onSelectedMessageIdsChange,
  onMessagesLoaded,
}: ZaloSupabaseLibraryPanelProps) {
  const [messages, setMessages] = useState<ZaloLibraryMessage[]>([]);
  const [filter, setFilter] = useState("");
  const [draft, setDraft] = useState<ZaloLibraryMessageCreateRequest>(emptyDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const selectedSet = useMemo(() => new Set(selectedMessageIds), [selectedMessageIds]);
  const totalPages = Math.max(1, Math.ceil(messages.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageMessages = useMemo(
    () => messages.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [currentPage, messages],
  );
  const pageMessageIds = pageMessages.map((message) => message.id);
  const isPageSelected = pageMessageIds.length > 0 && pageMessageIds.every((id) => selectedSet.has(id));

  const loadMessages = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getZaloLibraryMessages(userId, filter, 1000);
      setMessages(response.messages);
      onMessagesLoaded(response.messages);
      setPage(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tải thư viện tin nhắn.");
    } finally {
      setIsLoading(false);
    }
  }, [filter, onMessagesLoaded, userId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadMessages();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadMessages]);

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
        content,
        asset_urls: assetUrls,
      });
      setDraft(emptyDraft);
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
      onSelectedMessageIdsChange([]);
      await loadMessages();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể xóa hàng loạt.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeleteAllMatching() {
    const scope = filter.trim() ? `theo bộ lọc "${filter.trim()}"` : "toàn bộ thư viện";
    if (!window.confirm(`Xóa ${scope}? Hành động này là xóa mềm trong Supabase.`)) return;
    setIsSaving(true);
    setError(null);
    try {
      await bulkDeleteZaloLibraryMessages(userId, {
        group_name: filter.trim() || undefined,
        delete_all_matching: true,
      });
      onSelectedMessageIdsChange([]);
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
            Dữ liệu crawl được lưu trong Supabase. Chọn tin ở đây để đưa sang chiến dịch gửi.
          </p>
        </div>
        <div className="flex flex-col gap-sm sm:flex-row">
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Lọc theo nhóm"
            className="border-outline-variant bg-surface rounded-xl border px-md py-sm text-body-sm"
          />
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
          <input type="checkbox" checked={isPageSelected} onChange={togglePageSelected} disabled={pageMessages.length === 0} />
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
            disabled={messages.length === 0 || isSaving}
            className="border-error-container text-error inline-flex items-center gap-1 rounded-lg border px-sm py-xs text-body-sm font-semibold disabled:opacity-60"
          >
            <MaterialIcon name="delete" className="text-base" />
            {filter.trim() ? "Xóa theo bộ lọc" : "Xóa tất cả"}
          </button>
        </div>
      </div>

      <div className="mb-md flex flex-wrap items-center justify-between gap-sm text-body-sm text-on-surface-variant">
        <span>
          Hiển thị {pageMessages.length} / {messages.length} tin
        </span>
        <div className="flex items-center gap-sm">
          <button
            type="button"
            className="border-outline-variant rounded-lg border px-sm py-xs font-semibold disabled:opacity-50"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={currentPage <= 1}
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
            disabled={currentPage >= totalPages}
          >
            Sau
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-md">
        {messages.length === 0 ? (
          <div className="border-outline-variant bg-surface rounded-xl border px-md py-lg text-body-sm text-on-surface-variant">
            {isLoading ? "Đang tải thư viện..." : "Chưa có tin nhắn trong Supabase."}
          </div>
        ) : null}

        {pageMessages.map((message) => {
          const isSelected = selectedSet.has(message.id);
          const assets = uploadedAssets(message);
          const isEditing = editingId === message.id;
          return (
            <article
              key={message.id}
              className={`border-outline-variant bg-surface rounded-xl border p-md shadow-sm ${isSelected ? "ring-primary ring-2" : ""}`}
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
                      {message.sender_name || "Không rõ người gửi"} · {message.time_text || message.timestamp_text || "Không rõ thời gian"}
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
                    <a key={asset.id || asset.storage_url} href={asset.storage_url || "#"} target="_blank" rel="noreferrer">
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
    </section>
  );
}
