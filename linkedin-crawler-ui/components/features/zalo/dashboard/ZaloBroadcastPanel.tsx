"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";

import { MaterialIcon } from "@/components/ui";
import {
  createZaloBroadcast,
  getZaloBroadcast,
  getZaloCrawledGroups,
  getZaloLiveGroups,
  previewZaloBroadcast,
} from "@/services/zaloCrawlerService";
import type {
  ZaloBroadcastContentMode,
  ZaloBroadcastPreviewResponse,
  ZaloBroadcastStatusResponse,
  ZaloBroadcastTarget,
  ZaloCrawledGroupItem,
  ZaloLibraryMessage,
  ZaloLiveGroup,
} from "@/types/zalo-api";

interface ZaloBroadcastPanelProps {
  userId: string;
  selectedMessageIds: string[];
  selectedMessages: ZaloLibraryMessage[];
}

function normalizeSearchText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function normalizeTargets(
  conversations: ZaloLiveGroup[],
  manualText: string,
  selectedIds: string[],
): ZaloBroadcastTarget[] {
  const targets = new Map<string, ZaloBroadcastTarget>();

  for (const item of conversations) {
    if (!selectedIds.includes(item.group_id)) continue;
    const name = item.name.trim();
    const key = normalizeSearchText(name);
    if (!key) continue;
    targets.set(key, { group_id: item.group_id, group_name: name });
  }

  for (const line of manualText.split("\n")) {
    const name = line.trim();
    const key = normalizeSearchText(name);
    if (!key) continue;
    targets.set(key, { group_name: name });
  }

  return Array.from(targets.values());
}

function savedToLiveConversation(group: ZaloCrawledGroupItem): ZaloLiveGroup | null {
  const name = (group.group_name || group.sheet_tab || "").trim();
  if (!name) return null;
  return {
    group_id: name,
    name,
    avatar_url: null,
    last_message: `${group.message_count ?? 0} tin đã lưu`,
    unread_count: 0,
  };
}

function conversationKey(item: Pick<ZaloLiveGroup, "group_id" | "name">): string {
  return normalizeSearchText(item.name || item.group_id);
}

function mergeConversations(previous: ZaloLiveGroup[], incoming: ZaloLiveGroup[]): ZaloLiveGroup[] {
  const byKey = new Map<string, ZaloLiveGroup>();

  for (const item of previous) {
    const key = conversationKey(item);
    if (key) byKey.set(key, item);
  }

  for (const item of incoming) {
    const key = conversationKey(item);
    if (!key) continue;
    const existing = byKey.get(key);
    byKey.set(key, {
      ...existing,
      ...item,
      group_id: item.group_id || existing?.group_id || item.name,
      name: item.name || existing?.name || item.group_id,
      last_message: item.last_message || existing?.last_message || null,
    });
  }

  return Array.from(byKey.values()).sort((left, right) => left.name.localeCompare(right.name, "vi"));
}

function uploadedAssetCount(message: ZaloLibraryMessage | undefined): number {
  return (message?.assets || []).filter(
    (asset) => asset.status === "uploaded" && (asset.storage_url || asset.storage_path),
  ).length;
}

function publicAssetUrls(message: ZaloLibraryMessage | undefined): string[] {
  return (message?.assets || [])
    .filter((asset) => asset.status === "uploaded" && asset.storage_url)
    .map((asset) => asset.storage_url as string);
}

export function ZaloBroadcastPanel({
  userId,
  selectedMessageIds,
  selectedMessages,
}: ZaloBroadcastPanelProps) {
  const [contentMode, setContentMode] = useState<ZaloBroadcastContentMode>("both");
  const [liveConversations, setLiveConversations] = useState<ZaloLiveGroup[]>([]);
  const [selectedConversationIds, setSelectedConversationIds] = useState<string[]>([]);
  const [targetSearchText, setTargetSearchText] = useState("");
  const [manualTargets, setManualTargets] = useState("");
  const [preview, setPreview] = useState<ZaloBroadcastPreviewResponse | null>(null);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [campaignStatus, setCampaignStatus] = useState<ZaloBroadcastStatusResponse | null>(null);
  const [isLoadingTargets, setIsLoadingTargets] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedMessageKey = selectedMessageIds.join("|");

  const targets = useMemo(
    () => normalizeTargets(liveConversations, manualTargets, selectedConversationIds),
    [liveConversations, manualTargets, selectedConversationIds],
  );

  const visibleConversations = useMemo(() => {
    const keyword = normalizeSearchText(targetSearchText);
    if (!keyword) return liveConversations;
    return liveConversations.filter((item) => normalizeSearchText(item.name).includes(keyword));
  }, [liveConversations, targetSearchText]);

  const selectedLiveConversations = useMemo(
    () => liveConversations.filter((item) => selectedConversationIds.includes(item.group_id)),
    [liveConversations, selectedConversationIds],
  );

  const visibleSelectedCount = useMemo(
    () => visibleConversations.filter((item) => selectedConversationIds.includes(item.group_id)).length,
    [selectedConversationIds, visibleConversations],
  );

  const allVisibleSelected =
    visibleConversations.length > 0 && visibleSelectedCount === visibleConversations.length;

  useEffect(() => {
    setPreview(null);
  }, [contentMode, selectedMessageKey, targets]);

  useEffect(() => {
    let isCancelled = false;
    async function loadSavedTargets() {
      try {
        const response = await getZaloCrawledGroups(userId);
        if (isCancelled) return;
        const saved = response.groups
          .map(savedToLiveConversation)
          .filter((item): item is ZaloLiveGroup => item !== null);
        if (saved.length > 0) {
          setLiveConversations((current) => mergeConversations(current, saved));
        }
      } catch {
        // Saved targets are a convenience fallback; direct manual input still works.
      }
    }

    void loadSavedTargets();
    return () => {
      isCancelled = true;
    };
  }, [userId]);

  useEffect(() => {
    if (!campaignId) return;
    const timer = window.setInterval(async () => {
      try {
        const status = await getZaloBroadcast(campaignId);
        setCampaignStatus(status);
      } catch {
        // Polling errors are non-blocking; create/send errors are shown directly.
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [campaignId]);

  async function loadTargets() {
    setIsLoadingTargets(true);
    setError(null);
    try {
      const conversations = await getZaloLiveGroups(userId);
      setLiveConversations((current) => mergeConversations(current, conversations));
      if (conversations.length === 0) {
        setError("Zalo chưa trả thêm người nhận live. Danh sách đã crawl/lưu vẫn được giữ lại để chọn.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tải danh sách người nhận từ Zalo.");
    } finally {
      setIsLoadingTargets(false);
    }
  }

  async function handlePreview() {
    setIsPreviewing(true);
    setError(null);
    try {
      const result = await previewZaloBroadcast(userId, {
        user_id: userId,
        message_ids: selectedMessageIds,
        targets,
        content_mode: contentMode,
      });
      setPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tạo preview gửi.");
    } finally {
      setIsPreviewing(false);
    }
  }

  async function handleSend() {
    setIsSending(true);
    setError(null);
    try {
      const response = await createZaloBroadcast(userId, {
        user_id: userId,
        message_ids: selectedMessageIds,
        targets,
        content_mode: contentMode,
      });
      setCampaignId(response.campaign_id);
      setCampaignStatus(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tạo chiến dịch gửi.");
    } finally {
      setIsSending(false);
    }
  }

  function toggleVisibleTargets() {
    const visibleIds = visibleConversations.map((item) => item.group_id);
    if (allVisibleSelected) {
      setSelectedConversationIds((current) => current.filter((id) => !visibleIds.includes(id)));
      return;
    }
    setSelectedConversationIds((current) => Array.from(new Set([...current, ...visibleIds])));
  }

  const canPreview = selectedMessageIds.length > 0 && targets.length > 0;
  const canSend = canPreview && preview !== null && (preview.warnings?.length ?? 0) === 0;

  return (
    <section className="border-outline-variant bg-surface-container-lowest rounded-2xl border p-lg shadow-sm">
      <div className="mb-lg flex flex-col gap-md lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-h2 text-on-surface font-semibold">Chiến dịch gửi</h2>
          <p className="text-body-sm text-on-surface-variant">
            Chọn tin đã lưu, chọn group hoặc cá nhân, xem preview rồi gửi tuần tự qua phiên Zalo hiện tại.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadTargets()}
          disabled={isLoadingTargets}
          className="bg-primary text-on-primary inline-flex items-center justify-center gap-sm rounded-xl px-md py-sm text-body-sm font-semibold disabled:opacity-60"
        >
          <MaterialIcon name="group" className="text-base" />
          {isLoadingTargets ? "Đang tải" : "Tải người nhận Zalo"}
        </button>
      </div>

      {error ? (
        <div className="border-error-container bg-error-container/40 text-error mb-md rounded-xl border px-md py-sm text-body-sm">
          {error}
        </div>
      ) : null}

      <div className="grid gap-lg xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <div className="flex flex-col gap-md">
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-sm font-semibold uppercase">
              Nội dung gửi
            </div>
            <div className="grid gap-sm sm:grid-cols-3">
              {[
                ["both", "Text + ảnh"],
                ["text", "Chỉ text"],
                ["image", "Chỉ ảnh"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setContentMode(value as ZaloBroadcastContentMode)}
                  className={`border-outline-variant rounded-xl border px-md py-sm text-body-sm font-semibold ${
                    contentMode === value ? "bg-primary text-on-primary" : "bg-surface text-on-surface"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="text-body-sm text-on-surface-variant mt-sm">
              Đã chọn {selectedMessageIds.length} tin nhắn.
            </div>
          </div>

          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="text-label-md text-on-surface-variant mb-sm font-semibold uppercase">
              Người nhận
            </div>
            <textarea
              value={manualTargets}
              onChange={(event) => setManualTargets(event.target.value)}
              rows={4}
              placeholder="Nhập tên group hoặc cá nhân, mỗi dòng một người nhận"
              className="border-outline-variant mb-md w-full rounded-lg border px-md py-sm text-body-sm"
            />

            {liveConversations.length > 0 ? (
              <>
                <div className="mb-sm flex items-center gap-sm">
                  <MaterialIcon name="search" className="text-on-surface-variant text-lg" />
                  <input
                    value={targetSearchText}
                    onChange={(event) => setTargetSearchText(event.target.value)}
                    placeholder="Tìm group hoặc cá nhân để gửi"
                    className="border-outline-variant w-full rounded-lg border px-md py-sm text-body-sm"
                  />
                </div>

                <div className="mb-sm flex flex-wrap items-center justify-between gap-sm">
                  <div className="text-body-xs text-on-surface-variant">
                    Đang hiện {visibleConversations.length}/{liveConversations.length} cuộc trò chuyện, đã chọn{" "}
                    {selectedConversationIds.length}.
                  </div>
                  <div className="flex flex-wrap gap-sm">
                    <button
                      type="button"
                      onClick={toggleVisibleTargets}
                      disabled={visibleConversations.length === 0}
                      className="border-outline-variant rounded-lg border px-sm py-xs text-xs font-bold uppercase disabled:opacity-50"
                    >
                      {allVisibleSelected ? "Bỏ chọn kết quả" : "Chọn kết quả"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedConversationIds([])}
                      disabled={selectedConversationIds.length === 0}
                      className="border-outline-variant rounded-lg border px-sm py-xs text-xs font-bold uppercase disabled:opacity-50"
                    >
                      Bỏ chọn tất cả
                    </button>
                  </div>
                </div>

                <div className="grid max-h-80 gap-sm overflow-auto sm:grid-cols-2">
                  {visibleConversations.map((item) => (
                    <label
                      key={item.group_id}
                      className={`border-outline-variant flex gap-sm rounded-lg border px-sm py-xs text-body-sm ${
                        selectedConversationIds.includes(item.group_id)
                          ? "bg-primary-container text-on-primary-container"
                          : ""
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedConversationIds.includes(item.group_id)}
                        onChange={(event) => {
                          if (event.target.checked) {
                            setSelectedConversationIds((current) =>
                              current.includes(item.group_id) ? current : [...current, item.group_id],
                            );
                          } else {
                            setSelectedConversationIds((current) => current.filter((id) => id !== item.group_id));
                          }
                        }}
                      />
                      <span>{item.name}</span>
                    </label>
                  ))}
                </div>

                {selectedLiveConversations.length > 0 ? (
                  <div className="mt-md rounded-lg bg-surface-container-low px-md py-sm">
                    <div className="mb-xs text-xs font-bold uppercase text-on-surface-variant">
                      Đã chọn từ danh sách
                    </div>
                    <div className="flex flex-wrap gap-xs">
                      {selectedLiveConversations.map((item) => (
                        <button
                          key={item.group_id}
                          type="button"
                          onClick={() =>
                            setSelectedConversationIds((current) => current.filter((id) => id !== item.group_id))
                          }
                          className="border-outline-variant inline-flex items-center gap-1 rounded-full border bg-surface px-sm py-0.5 text-xs font-semibold"
                        >
                          {item.name}
                          <MaterialIcon name="close" className="text-sm" />
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                {visibleConversations.length === 0 ? (
                  <div className="text-body-sm text-on-surface-variant mt-sm">
                    Không tìm thấy người nhận phù hợp. Có thể nhập tên thủ công ở ô bên trên.
                  </div>
                ) : null}
              </>
            ) : (
              <div className="text-body-sm text-on-surface-variant">
                Có thể nhập người nhận thủ công hoặc tải danh sách sau khi đã đăng nhập Zalo.
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-md">
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="mb-sm flex items-center justify-between gap-sm">
              <div>
                <div className="text-label-md text-on-surface-variant font-semibold uppercase">Preview</div>
                <div className="text-body-sm text-on-surface-variant">
                  {targets.length} người nhận · {selectedMessageIds.length} tin
                </div>
              </div>
              <button
                type="button"
                onClick={() => void handlePreview()}
                disabled={!canPreview || isPreviewing}
                className="border-outline-variant inline-flex items-center gap-sm rounded-xl border px-md py-sm text-body-sm font-semibold disabled:opacity-60"
              >
                <MaterialIcon name="visibility" className="text-base" />
                Preview
              </button>
            </div>

            {preview ? (
              <div className="flex flex-col gap-sm">
                {preview.warnings.map((warning) => (
                  <div
                    key={warning}
                    className="border-error-container bg-error-container/40 text-error rounded-lg border px-sm py-xs text-body-sm"
                  >
                    {warning}
                  </div>
                ))}
                {preview.items.map((item) => {
                  const message = selectedMessages.find((candidate) => candidate.id === item.message_id);
                  const previewUrls = item.image_urls?.length ? item.image_urls : publicAssetUrls(message);
                  const realImageCount = Math.max(item.image_count, uploadedAssetCount(message));
                  return (
                    <div key={item.message_id} className="border-outline-variant rounded-lg border px-sm py-xs">
                      <div className="text-body-sm text-on-surface font-semibold">
                        {item.send_text ? "Gửi text" : "Không gửi text"} ·{" "}
                        {item.send_images ? `${realImageCount} ảnh` : "Không gửi ảnh"}
                      </div>
                      <div className="text-body-sm text-on-surface-variant whitespace-pre-wrap">
                        {message?.content || item.content || "Không có nội dung text"}
                      </div>
                      {realImageCount > 0 ? (
                        <div className="mt-sm grid gap-sm sm:grid-cols-3">
                          {previewUrls.map((url) => (
                            <Image
                              key={url}
                              src={url}
                              alt="Ảnh sẽ gửi"
                              width={180}
                              height={120}
                              unoptimized
                              className="border-outline-variant aspect-video w-full rounded-lg border object-cover"
                            />
                          ))}
                          {previewUrls.length === 0 ? (
                            <div className="border-outline-variant bg-surface-container-low rounded-lg border px-sm py-xs text-body-sm text-on-surface-variant">
                              Có {realImageCount} ảnh đã lưu và sẽ gửi, nhưng bucket không public nên không có ảnh
                              preview.
                            </div>
                          ) : null}
                        </div>
                      ) : null}
                      {item.warnings.length > 0 ? (
                        <div className="text-error mt-xs text-body-sm">{item.warnings.join("; ")}</div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-body-sm text-on-surface-variant">
                Bấm Preview trước khi gửi để kiểm tra nội dung và người nhận.
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={!canSend || isSending}
            className="bg-primary text-on-primary inline-flex items-center justify-center gap-sm rounded-xl px-lg py-md text-body-md font-semibold disabled:opacity-60"
          >
            <MaterialIcon name="share" className="text-lg" />
            {isSending ? "Đang tạo chiến dịch" : "Gửi hàng loạt"}
          </button>

          {campaignId ? (
            <div className="border-outline-variant bg-surface rounded-xl border p-md">
              <div className="text-body-sm text-on-surface font-semibold">Campaign: {campaignId}</div>
              <div className="text-body-sm text-on-surface-variant">
                Trạng thái: {String(campaignStatus?.campaign?.status ?? "queued")}
              </div>
              <div className="mt-sm flex max-h-72 flex-col gap-xs overflow-auto">
                {(campaignStatus?.logs ?? []).map((log, index) => (
                  <div key={`${String(log.id ?? index)}`} className="text-body-sm text-on-surface-variant">
                    {String(log.status)} · {String(log.group_name || "")} · {String(log.detail || "")}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
