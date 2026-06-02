"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";

import { MaterialIcon } from "@/components/ui";
import {
  createZaloBroadcast,
  getZaloBroadcast,
  getZaloLiveGroups,
  previewZaloBroadcast,
} from "@/services/zaloCrawlerService";
import type {
  ZaloBroadcastContentMode,
  ZaloBroadcastPreviewResponse,
  ZaloBroadcastStatusResponse,
  ZaloBroadcastTarget,
  ZaloLibraryMessage,
  ZaloLiveGroup,
} from "@/types/zalo-api";

interface ZaloBroadcastPanelProps {
  userId: string;
  selectedMessageIds: string[];
  selectedMessages: ZaloLibraryMessage[];
}

function normalizeTargets(groups: ZaloLiveGroup[], manualText: string, selectedIds: string[]): ZaloBroadcastTarget[] {
  const targets = new Map<string, ZaloBroadcastTarget>();
  for (const group of groups) {
    if (selectedIds.includes(group.group_id)) {
      targets.set(group.name.trim().toLowerCase(), {
        group_id: group.group_id,
        group_name: group.name,
      });
    }
  }
  for (const line of manualText.split("\n")) {
    const name = line.trim();
    if (name) {
      targets.set(name.toLowerCase(), { group_name: name });
    }
  }
  return Array.from(targets.values());
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

function normalizeSearchText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function ZaloBroadcastPanel({
  userId,
  selectedMessageIds,
  selectedMessages,
}: ZaloBroadcastPanelProps) {
  const [contentMode, setContentMode] = useState<ZaloBroadcastContentMode>("both");
  const [liveGroups, setLiveGroups] = useState<ZaloLiveGroup[]>([]);
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>([]);
  const [targetSearchText, setTargetSearchText] = useState("");
  const [manualTargets, setManualTargets] = useState("");
  const [preview, setPreview] = useState<ZaloBroadcastPreviewResponse | null>(null);
  const [campaignId, setCampaignId] = useState<string | null>(null);
  const [campaignStatus, setCampaignStatus] = useState<ZaloBroadcastStatusResponse | null>(null);
  const [isLoadingGroups, setIsLoadingGroups] = useState(false);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targets = useMemo(
    () => normalizeTargets(liveGroups, manualTargets, selectedGroupIds),
    [liveGroups, manualTargets, selectedGroupIds],
  );

  const visibleLiveGroups = useMemo(() => {
    const keyword = normalizeSearchText(targetSearchText);
    if (!keyword) return liveGroups;
    return liveGroups.filter((group) => normalizeSearchText(group.name).includes(keyword));
  }, [liveGroups, targetSearchText]);

  useEffect(() => {
    if (!campaignId) return;
    const timer = window.setInterval(async () => {
      try {
        const status = await getZaloBroadcast(campaignId);
        setCampaignStatus(status);
      } catch {
        // Keep polling lightweight; explicit errors are shown when creating campaign.
      }
    }, 2500);
    return () => window.clearInterval(timer);
  }, [campaignId]);

  async function loadGroups() {
    setIsLoadingGroups(true);
    setError(null);
    try {
      const groups = await getZaloLiveGroups(userId);
      setLiveGroups(groups);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể tải danh sách group Zalo.");
    } finally {
      setIsLoadingGroups(false);
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

  const canPreview = selectedMessageIds.length > 0 && targets.length > 0;
  const canSend = canPreview && preview !== null && (preview.warnings?.length ?? 0) === 0;

  return (
    <section className="border-outline-variant bg-surface-container-lowest rounded-2xl border p-lg shadow-sm">
      <div className="mb-lg flex flex-col gap-md lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-h2 text-on-surface font-semibold">Chiến dịch gửi</h2>
          <p className="text-body-sm text-on-surface-variant">
            Chọn tin đã lưu, chọn group đích, xem preview rồi gửi tuần tự qua phiên Zalo hiện tại.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadGroups()}
          disabled={isLoadingGroups}
          className="bg-primary text-on-primary inline-flex items-center justify-center gap-sm rounded-xl px-md py-sm text-body-sm font-semibold disabled:opacity-60"
        >
          <MaterialIcon name="group" className="text-base" />
          {isLoadingGroups ? "Đang tải" : "Tải group Zalo"}
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
              Group đích
            </div>
            <textarea
              value={manualTargets}
              onChange={(event) => setManualTargets(event.target.value)}
              rows={4}
              placeholder="Nhập tên group, mỗi dòng một group"
              className="border-outline-variant mb-md w-full rounded-lg border px-md py-sm text-body-sm"
            />
            {liveGroups.length > 0 ? (
              <>
                <div className="mb-sm flex items-center gap-sm">
                  <MaterialIcon name="search" className="text-on-surface-variant text-lg" />
                  <input
                    value={targetSearchText}
                    onChange={(event) => setTargetSearchText(event.target.value)}
                    placeholder="Tim group dich de gui"
                    className="border-outline-variant w-full rounded-lg border px-md py-sm text-body-sm"
                  />
                </div>
                <div className="text-body-xs text-on-surface-variant mb-sm">
                  Dang hien {visibleLiveGroups.length}/{liveGroups.length} group, da chon {selectedGroupIds.length}.
                </div>
                <div className="grid max-h-80 gap-sm overflow-auto sm:grid-cols-2">
                  {visibleLiveGroups.map((group) => (
                    <label key={group.group_id} className="border-outline-variant flex gap-sm rounded-lg border px-sm py-xs text-body-sm">
                      <input
                        type="checkbox"
                        checked={selectedGroupIds.includes(group.group_id)}
                        onChange={(event) => {
                          if (event.target.checked) {
                            setSelectedGroupIds((current) =>
                              current.includes(group.group_id) ? current : [...current, group.group_id],
                            );
                          } else {
                            setSelectedGroupIds((current) => current.filter((id) => id !== group.group_id));
                          }
                        }}
                      />
                      <span>{group.name}</span>
                    </label>
                  ))}
                </div>
                {visibleLiveGroups.length === 0 ? (
                  <div className="text-body-sm text-on-surface-variant mt-sm">
                    Khong tim thay group phu hop. Co the nhap ten group thu cong o o ben tren.
                  </div>
                ) : null}
              </>
            ) : (
              <div className="text-body-sm text-on-surface-variant">
                Có thể nhập group thủ công hoặc tải danh sách group sau khi đã đăng nhập Zalo.
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-md">
          <div className="border-outline-variant bg-surface rounded-xl border p-md">
            <div className="mb-sm flex items-center justify-between gap-sm">
              <div>
                <div className="text-label-md text-on-surface-variant font-semibold uppercase">
                  Preview
                </div>
                <div className="text-body-sm text-on-surface-variant">
                  {targets.length} group đích · {selectedMessageIds.length} tin
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
                  <div key={warning} className="border-error-container bg-error-container/40 text-error rounded-lg border px-sm py-xs text-body-sm">
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
                        {item.send_text ? "Gửi text" : "Không gửi text"} · {item.send_images ? `${realImageCount} ảnh` : "Không gửi ảnh"}
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
                              Có {realImageCount} ảnh đã lưu và sẽ gửi, nhưng bucket không public nên không có ảnh preview.
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
                Bấm Preview trước khi gửi để kiểm tra nội dung và group đích.
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
