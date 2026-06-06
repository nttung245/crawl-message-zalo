"use client";

import { useEffect, useMemo, useState } from "react";

import { MaterialIcon } from "@/components/ui";
import type { ZaloCrawlerFlowValue } from "@/hooks/useZaloCrawlerFlow";
import { getZaloLiveGroups } from "@/services/zaloCrawlerService";
import type { ZaloCrawledGroupItem, ZaloLiveGroup } from "@/types/zalo-api";

interface ZaloLiveGroupPickerProps {
  flow: ZaloCrawlerFlowValue;
}

function normalizeSearch(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function liveToCrawlItem(group: ZaloLiveGroup): ZaloCrawledGroupItem {
  return {
    group_name: group.name,
    sheet_tab: group.name,
    message_count: 0,
  };
}

function savedToLiveGroup(group: ZaloCrawledGroupItem): ZaloLiveGroup {
  const groupName = group.group_name.trim() || group.sheet_tab.trim();
  return {
    group_id: groupName,
    name: groupName,
    avatar_url: null,
    last_message: `${group.message_count ?? 0} tin da luu`,
    unread_count: 0,
  };
}

function groupKey(group: Pick<ZaloLiveGroup, "name" | "group_id">): string {
  return normalizeSearch(group.name || group.group_id);
}

function mergeGroups(previous: ZaloLiveGroup[], incoming: ZaloLiveGroup[]): ZaloLiveGroup[] {
  const byKey = new Map<string, ZaloLiveGroup>();
  for (const group of previous) {
    const key = groupKey(group);
    if (key) byKey.set(key, group);
  }
  for (const group of incoming) {
    const key = groupKey(group);
    if (!key) continue;
    const existing = byKey.get(key);
    byKey.set(key, {
      ...existing,
      ...group,
      group_id: group.group_id || existing?.group_id || group.name,
      name: group.name || existing?.name || group.group_id,
      last_message: group.last_message || existing?.last_message || null,
    });
  }
  return Array.from(byKey.values()).sort((left, right) =>
    left.name.localeCompare(right.name, "vi"),
  );
}

export function ZaloLiveGroupPicker({ flow }: ZaloLiveGroupPickerProps) {
  const [groups, setGroups] = useState<ZaloLiveGroup[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [searchText, setSearchText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const savedGroups = flow.crawledGroups
      .filter((group) => group.group_name.trim() || group.sheet_tab.trim())
      .map(savedToLiveGroup);
    if (savedGroups.length === 0) return;
    setGroups((current) => mergeGroups(current, savedGroups));
  }, [flow.crawledGroups]);

  const visibleGroups = useMemo(() => {
    const needle = normalizeSearch(searchText);
    if (!needle) return groups;
    return groups.filter((group) => normalizeSearch(group.name).includes(needle));
  }, [groups, searchText]);

  async function loadGroups() {
    if (!flow.hasConfirmedSession) {
      setError("Cần đăng nhập Zalo trước khi tải danh sách nhóm.");
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const liveGroups = await getZaloLiveGroups(flow.userId);
      setGroups((current) => mergeGroups(current, liveGroups));
      if (liveGroups.length === 0) {
        setError("Không thấy nhóm nào. Zalo có thể chưa đồng bộ xong, hãy thử lại sau vài giây.");
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? `Không thể tải nhóm live từ Zalo. ${err.message}`
          : "Không thể tải nhóm live từ Zalo.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  function toggleGroup(groupId: string) {
    setSelectedIds((current) =>
      current.includes(groupId)
        ? current.filter((id) => id !== groupId)
        : [...current, groupId],
    );
  }

  function addSelectedGroups() {
    const selected = groups.filter((group) => selectedIds.includes(group.group_id));
    for (const group of selected) {
      flow.addCrawledGroup(liveToCrawlItem(group));
    }
    setSelectedIds([]);
  }

  return (
    <div className="border-outline-variant bg-surface-container-low mb-md rounded-xl border p-md">
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <div>
          <div className="text-label-md font-semibold uppercase text-on-surface-variant">
            Chọn nhóm từ Zalo
          </div>
          <div className="text-body-sm text-on-surface-variant">
            Bấm tải nhóm, tick nhóm cần crawl, rồi thêm vào danh sách chạy.
          </div>
          <div className="text-body-sm text-on-surface-variant">
            Danh sach da luu luon duoc giu lai; goi y tu Zalo chi merge them.
          </div>
        </div>
        <button
          type="button"
          className="bg-primary text-on-primary inline-flex min-h-10 items-center gap-2 rounded-lg px-md py-xs text-xs font-bold uppercase disabled:cursor-not-allowed disabled:opacity-60"
          onClick={() => void loadGroups()}
          disabled={!flow.hasConfirmedSession || isLoading || flow.isSubmittingGroups}
        >
          <MaterialIcon name={isLoading ? "sync" : "refresh"} className={`text-base ${isLoading ? "animate-spin" : ""}`} />
          {isLoading ? "Đang tải nhóm" : groups.length > 0 ? "Tải lại nhóm" : "Tải nhóm từ Zalo"}
        </button>
      </div>

      <div className="mt-md flex flex-col gap-md">
        {!flow.hasConfirmedSession ? (
          <div className="border-outline-variant bg-surface rounded-lg border px-md py-sm text-body-sm text-on-surface-variant">
            Đăng nhập Zalo xong mới tải được danh sách nhóm live.
          </div>
        ) : null}

        {error ? (
          <div className="border-error-container bg-error-container/40 text-error rounded-lg border px-md py-sm text-body-sm">
            {error}
          </div>
        ) : null}

        <div className="flex flex-col gap-sm sm:flex-row">
          <div className="relative min-w-0 flex-1">
            <MaterialIcon name="search" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-base text-on-surface-variant" />
            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Tìm nhóm theo tên"
              className="border-outline-variant bg-surface min-h-11 w-full rounded-lg border py-sm pl-10 pr-md text-body-sm"
              disabled={groups.length === 0}
            />
          </div>
          <button
            type="button"
            className="border-outline-variant bg-surface hover:bg-surface-container-high min-h-11 rounded-lg border px-md py-sm text-body-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
            onClick={addSelectedGroups}
            disabled={selectedIds.length === 0 || flow.isSubmittingGroups}
          >
            Thêm {selectedIds.length > 0 ? selectedIds.length : ""} nhóm vào crawl
          </button>
        </div>

        {groups.length === 0 ? (
          <div className="border-outline-variant bg-surface rounded-lg border px-md py-lg text-body-sm text-on-surface-variant">
            {isLoading ? "Đang tải danh sách nhóm..." : "Chưa có danh sách nhóm. Bấm “Tải nhóm từ Zalo” để bắt đầu."}
          </div>
        ) : visibleGroups.length === 0 ? (
          <div className="border-outline-variant bg-surface rounded-lg border px-md py-lg text-body-sm text-on-surface-variant">
            Không tìm thấy nhóm phù hợp với từ khóa.
          </div>
        ) : (
          <div className="grid max-h-80 gap-sm overflow-y-auto pr-1 sm:grid-cols-2">
            {visibleGroups.map((group) => {
              const checked = selectedIds.includes(group.group_id);
              return (
                <label
                  key={`${group.group_id}-${group.name}`}
                  className={`border-outline-variant bg-surface flex cursor-pointer gap-sm rounded-lg border px-md py-sm text-left transition ${
                    checked ? "ring-primary ring-2" : "hover:bg-surface-container-high"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleGroup(group.group_id)}
                    className="mt-1 h-4 w-4"
                  />
                  <span className="min-w-0">
                    <span className="block truncate text-body-sm font-semibold text-on-surface">
                      {group.name}
                    </span>
                    {group.last_message ? (
                      <span className="line-clamp-2 text-body-sm text-on-surface-variant">
                        {group.last_message}
                      </span>
                    ) : null}
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
