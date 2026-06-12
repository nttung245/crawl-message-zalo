"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  getZaloCrawledGroups,
  previewAgentExtract,
  testAgentExtract,
  villaSync,
} from "@/services/zaloCrawlerService";
import type { VillaSyncResponse } from "@/services/zaloCrawlerService";
import { useAgentTestSSE } from "@/hooks/useAgentTestSSE";
import type {
  AgentPreviewListing,
  AgentPreviewResponse,
  AgentTestExtractResponse,
  AgentTestExtractResult,
  AgentTestProgress,
  ZaloCrawledGroupItem,
} from "@/types/zalo-api";

type InputMode = "fake" | "text" | "group" | "villa-sync";

interface FakeGroup {
  group_name: string;
  messages: { id: string; text: string; images: string[] }[];
}

interface FakeDataResponse {
  groups: FakeGroup[];
  total_messages: number;
  total_images: number;
}

export function ZaloAgentTestPanel({ userId }: { userId: string }) {
  const [mode, setMode] = useState<InputMode>("fake");
  const [pasteText, setPasteText] = useState("");
  const [generatingFake, setGeneratingFake] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fakeData, setFakeData] = useState<FakeDataResponse | null>(null);
  const [selectedFakeGroup, setSelectedFakeGroup] = useState<string>("all");
  const {
    results,
    progress,
    summary,
    isStreaming,
    error: streamError,
    startStream,
    reset: resetStream,
    timedOut,
  } = useAgentTestSSE();

  // Crawled groups state
  const [crawledGroups, setCrawledGroups] = useState<ZaloCrawledGroupItem[]>([]);
  const [selectedCrawledGroup, setSelectedCrawledGroup] = useState<string>("");
  const [loadingGroups, setLoadingGroups] = useState(false);
  const [groupsError, setGroupsError] = useState<string | null>(null);

  // Villa sync state
  const [villaSyncResult, setVillaSyncResult] = useState<VillaSyncResponse | null>(null);
  const [villaSyncLoading, setVillaSyncLoading] = useState(false);
  const [villaSyncError, setVillaSyncError] = useState<string | null>(null);

  // Preview state
  const [previewData, setPreviewData] = useState<AgentPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [lastTestRequest, setLastTestRequest] = useState<{ texts?: string[]; group_name?: string } | null>(null);
  const [previewSyncLoading, setPreviewSyncLoading] = useState(false);
  const [syncedIds, setSyncedIds] = useState<Set<string>>(new Set());

  const handleGenerateFake = useCallback(async () => {
    setGeneratingFake(true);
    setError(null);

    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL}/api/apartment-agent/create-fake-data`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-API-Key": process.env.NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY || "",
          },
        },
      );

      if (!res.ok) {
        throw new Error(`API ${res.status}: ${res.statusText}`);
      }

      let data: FakeDataResponse;
      try {
        data = await res.json();
      } catch {
        throw new Error(
          `API ${res.status}: phản hồi không phải JSON (${process.env.NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL}/api/apartment-agent/create-fake-data)`,
        );
      }
      setFakeData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi không xác định");
    } finally {
      setGeneratingFake(false);
    }
  }, []);

  const handleTestFake = useCallback(async () => {
    if (!fakeData) return;

    setError(null);
    setPreviewData(null);
    setSelectedIds(new Set());
    setSyncedIds(new Set());

    const groupsToTest =
      selectedFakeGroup === "all"
        ? fakeData.groups
        : fakeData.groups.filter((g) => g.group_name === selectedFakeGroup);

    const allTexts = groupsToTest.flatMap((g) => g.messages.map((m) => m.text));
    setLastTestRequest({ texts: allTexts });
    startStream({ texts: allTexts });
  }, [fakeData, selectedFakeGroup, startStream]);

  const handleTestText = useCallback(async () => {
    const texts = pasteText
      .split("\n")
      .filter((t) => t.trim());

    if (texts.length === 0) {
      setError("Vui lòng nhập text");
      return;
    }

    setError(null);
    setPreviewData(null);
    setSelectedIds(new Set());
    setSyncedIds(new Set());

    setLastTestRequest({ texts });
    startStream({ texts });
  }, [pasteText, startStream]);

  // Load crawled groups when switching to "group" mode
  const loadCrawledGroups = useCallback(async () => {
    setLoadingGroups(true);
    setGroupsError(null);
    try {
      const response = await getZaloCrawledGroups(userId);
      setCrawledGroups(response.groups ?? []);
      if (response.groups?.length && !selectedCrawledGroup) {
        setSelectedCrawledGroup(response.groups[0].group_name);
      }
    } catch (err) {
      setGroupsError(err instanceof Error ? err.message : "Lỗi tải nhóm");
    } finally {
      setLoadingGroups(false);
    }
  }, [userId, selectedCrawledGroup]);

  const handleTestGroup = useCallback(async () => {
    if (!selectedCrawledGroup) {
      setError("Vui lòng chọn nhóm");
      return;
    }

    setError(null);
    setPreviewData(null);
    setSelectedIds(new Set());
    setSyncedIds(new Set());

    setLastTestRequest({ group_name: selectedCrawledGroup });
    startStream({ group_name: selectedCrawledGroup });
  }, [selectedCrawledGroup, startStream]);

  // Auto-load crawled groups when switching to "group" mode
  useEffect(() => {
    if (mode === "group" && crawledGroups.length === 0 && !loadingGroups) {
      void loadCrawledGroups();
    }
  }, [mode, crawledGroups.length, loadingGroups, loadCrawledGroups]);

  // Villa sync handlers
  const handleVillaSync = useCallback(async (dryRun: boolean) => {
    setVillaSyncLoading(true);
    setVillaSyncError(null);
    setVillaSyncResult(null);

    try {
      const res = await villaSync({ user_id: userId, dry_run: dryRun });
      setVillaSyncResult(res);
    } catch (err) {
      setVillaSyncError(err instanceof Error ? err.message : "Lỗi không xác định");
    } finally {
      setVillaSyncLoading(false);
    }
  }, [userId]);

  // Preview handlers
  const handleCreatePreview = useCallback(async () => {
    if (!lastTestRequest) return;

    setPreviewLoading(true);
    setPreviewError(null);
    setPreviewData(null);
    setSelectedIds(new Set());
    setSyncedIds(new Set());

    try {
      const res = await previewAgentExtract(lastTestRequest);
      setPreviewData(res);
      // Default: select INSERT listings, deselect UPDATE/SKIP
      const ids = new Set<string>();
      for (const l of res.listings) {
        if (l.operation === "insert") {
          ids.add(l.raw_message_id);
        }
      }
      setSelectedIds(ids);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Lỗi không xác định");
    } finally {
      setPreviewLoading(false);
    }
  }, [lastTestRequest]);

  const handleSendSelected = useCallback(async () => {
    if (selectedIds.size === 0) return;

    setPreviewSyncLoading(true);
    try {
      const res = await villaSync({
        user_id: userId,
        dry_run: false,
        listing_ids: Array.from(selectedIds),
      });
      setSyncedIds(new Set(selectedIds));
      toast.success(`Đã gửi ${selectedIds.size} listing`, {
        description: `${res.new_villas_created} created, ${res.villas_updated} updated`,
      });
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Lỗi không xác định");
      toast.error("Gửi thất bại", {
        description: err instanceof Error ? err.message : "Lỗi không xác định",
      });
    } finally {
      setPreviewSyncLoading(false);
    }
  }, [selectedIds, userId]);

  const previewInsertCount = useMemo(
    () => previewData?.listings.filter((l) => l.operation === "insert").length ?? 0,
    [previewData],
  );

  return (
    <div className="flex flex-col gap-lg">
      <div>
        <h2 className="text-h3 font-semibold text-on-surface">Test Apartment Agent</h2>
        <p className="text-body-md text-on-surface-variant">
          Kiểm tra khả năng extract dữ liệu từ tin nhắn Zalo (không sync Supabase)
        </p>
      </div>

      {/* Input Mode Selector */}
      <div className="border-outline-variant bg-surface-container-lowest flex gap-sm rounded-2xl border p-sm">
        {[
          ["fake", "🧪 Dữ liệu ảo"],
          ["text", "📝 Paste text"],
          ["group", "📋 Chọn nhóm đã crawl"],
          ["villa-sync", "🏠 Villa Sync"],
        ].map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setMode(value as InputMode)}
            className={`rounded-xl px-md py-sm text-body-sm font-semibold transition ${
              mode === value
                ? "bg-primary text-on-primary"
                : "text-on-surface hover:bg-surface-container-high"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── FAKE DATA MODE ─────────────────────────────────── */}
      {mode === "fake" && (
        <div className="flex flex-col gap-md">
          {!fakeData ? (
            <>
              <p className="text-body-sm text-on-surface-variant">
                Tạo 3 nhóm ảo với tin nhắn BĐS mẫu (có cả tin không phải BĐS) để test Agent.
              </p>
              <button
                type="button"
                onClick={handleGenerateFake}
                disabled={generatingFake}
                className="bg-tertiary text-on-tertiary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
              >
                {generatingFake ? "Đang tạo..." : "🎲 Tạo dữ liệu ảo để test Agent"}
              </button>
            </>
          ) : (
            <>
              {/* Fake data summary */}
              <div className="border-outline-variant bg-surface-container-low rounded-xl border p-md">
                <h3 className="text-h4 font-semibold text-on-surface mb-sm">
                  Dữ liệu ảo đã tạo
                </h3>
                <div className="grid grid-cols-3 gap-md text-center mb-md">
                  <div>
                    <div className="text-h3 font-bold text-primary">{fakeData.groups.length}</div>
                    <div className="text-body-sm text-on-surface-variant">Nhóm</div>
                  </div>
                  <div>
                    <div className="text-h3 font-bold text-secondary">{fakeData.total_messages}</div>
                    <div className="text-body-sm text-on-surface-variant">Tin nhắn</div>
                  </div>
                  <div>
                    <div className="text-h3 font-bold text-outline">{fakeData.total_images}</div>
                    <div className="text-body-sm text-on-surface-variant">Ảnh</div>
                  </div>
                </div>

                {/* Group list */}
                <div className="flex flex-col gap-sm">
                  {fakeData.groups.map((g) => (
                    <div
                      key={g.group_name}
                      className="bg-surface-container-lowest rounded-lg px-md py-sm text-body-sm"
                    >
                      <span className="font-semibold text-on-surface">{g.group_name}</span>
                      <span className="text-on-surface-variant">
                        {" "}
                        — {g.messages.length} tin, {g.messages.reduce((s, m) => s + m.images.length, 0)} ảnh
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Group selector for test */}
              <div className="flex flex-col gap-sm">
                <label className="text-body-sm font-medium text-on-surface">Chọn nhóm để test</label>
                <select
                  value={selectedFakeGroup}
                  onChange={(e) => setSelectedFakeGroup(e.target.value)}
                  className="border-outline bg-surface-container-lowest rounded-xl border px-md py-sm text-body-md"
                >
                  <option value="all">Tất cả ({fakeData.total_messages} tin)</option>
                  {fakeData.groups.map((g) => (
                    <option key={g.group_name} value={g.group_name}>
                      {g.group_name} ({g.messages.length} tin)
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex gap-sm">
                <button
                  type="button"
                  onClick={handleTestFake}
                  disabled={isStreaming}
                  className="bg-primary text-on-primary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
                >
                {isStreaming ? "Đang test..." : "🚀 Test Agent"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setFakeData(null);
                  resetStream();
                }}
                  className="border-outline text-on-surface rounded-xl border px-md py-sm text-body-sm transition hover:bg-surface-container-high"
                >
                  Tạo lại
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── TEXT MODE ─────────────────────────────────── */}
      {mode === "text" && (
        <div className="flex flex-col gap-sm">
          <label className="text-body-sm font-medium text-on-surface">
            Paste tin nhắn (mỗi dòng 1 tin)
          </label>
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            rows={6}
            placeholder="Cho thuê căn hộ 2PN, quận Hải Châu, 10tr/tháng..."
            className="border-outline bg-surface-container-lowest rounded-xl border px-md py-sm text-body-md"
          />
          <button
            type="button"
            onClick={handleTestText}
            disabled={isStreaming}
            className="bg-primary text-on-primary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50 self-start"
          >
            {isStreaming ? "Đang test..." : "🚀 Test Agent"}
          </button>
        </div>
      )}

      {/* ── GROUP MODE ─────────────────────────────────── */}
      {mode === "group" && (
        <div className="flex flex-col gap-md">
          <p className="text-body-sm text-on-surface-variant">
            Chọn nhóm đã crawl để test Agent trên dữ liệu thật. Hệ thống sẽ lấy tối đa 50 tin nhắn từ nhóm đã chọn.
          </p>

          {loadingGroups ? (
            <div className="text-body-sm text-on-surface-variant">Đang tải danh sách nhóm...</div>
          ) : groupsError ? (
            <div className="border-error-container bg-error-container/40 text-error rounded-lg border px-md py-sm text-body-sm">
              {groupsError}
            </div>
          ) : crawledGroups.length === 0 ? (
            <div className="text-body-sm text-on-surface-variant">
              Chưa có nhóm nào được crawl. Hãy chạy crawl trước ở tab "Crawl".
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-sm">
                <label className="text-body-sm font-medium text-on-surface">Chọn nhóm</label>
                <select
                  value={selectedCrawledGroup}
                  onChange={(e) => setSelectedCrawledGroup(e.target.value)}
                  className="border-outline bg-surface-container-lowest rounded-xl border px-md py-sm text-body-md"
                >
                  {crawledGroups.map((g) => (
                    <option key={g.group_name} value={g.group_name}>
                      {g.group_name} ({g.message_count} tin)
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex gap-sm">
                <button
                  type="button"
                  onClick={handleTestGroup}
                  disabled={isStreaming || !selectedCrawledGroup}
                  className="bg-primary text-on-primary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
                >
                  {isStreaming ? "Đang test..." : "🚀 Test Agent"}
                </button>
                <button
                  type="button"
                  onClick={() => void loadCrawledGroups()}
                  disabled={loadingGroups}
                  className="border-outline text-on-surface rounded-xl border px-md py-sm text-body-sm transition hover:bg-surface-container-high"
                >
                  Tải lại nhóm
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Error */}
      {(error || streamError || timedOut) && (
        <div className="border-error-container bg-error-container/40 rounded-xl border px-md py-sm text-body-sm text-error">
          {timedOut
            ? "Yêu cầu đã hết thời gian chờ. Hệ thống vẫn đang xử lý nhưng chưa kịp trả kết quả."
            : error || streamError}
          {timedOut && (
            <button
              type="button"
              onClick={() => {
                setError(null);
                resetStream();
              }}
              className="bg-error-container text-on-error-container ml-sm rounded-lg px-md py-0.5 text-body-xs font-semibold transition hover:opacity-80"
            >
              Thử lại
            </button>
          )}
        </div>
      )}

      {/* ── VILLA SYNC MODE ─────────────────────────────────── */}
      {mode === "villa-sync" && (
        <div className="flex flex-col gap-md">
          <p className="text-body-sm text-on-surface-variant">
            Sync apartment listings từ Zalo messages sang GoDaNang Supabase villas table.
            Pipeline: Fetch messages → LLM extract → Dedup → POST/PUT.
          </p>

          <div className="flex gap-sm">
            <button
              type="button"
              onClick={() => void handleVillaSync(true)}
              disabled={villaSyncLoading}
              className="bg-tertiary text-on-tertiary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
            >
              {villaSyncLoading ? "Đang chạy..." : "🔍 Dry Run (Preview)"}
            </button>
            <button
              type="button"
              onClick={() => void handleVillaSync(false)}
              disabled={villaSyncLoading}
              className="bg-primary text-on-primary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
            >
              {villaSyncLoading ? "Đang chạy..." : "🚀 Real Sync"}
            </button>
          </div>

          {/* Villa Sync Error */}
          {villaSyncError && (
            <div className="border-error-container bg-error-container/40 rounded-xl border px-md py-sm text-body-sm text-error">
              {villaSyncError}
            </div>
          )}

          {/* Villa Sync Results */}
          {villaSyncResult && (
            <div className="border-outline-variant bg-surface-container-low rounded-xl border p-md">
              <h3 className="text-h4 font-semibold text-on-surface mb-sm">
                Kết quả Villa Sync {villaSyncResult.dry_run && "(Dry Run)"}
              </h3>
              <div className="grid grid-cols-3 gap-md text-center mb-md md:grid-cols-5">
                <div>
                  <div className="text-h3 font-bold text-primary">{villaSyncResult.total_messages_processed}</div>
                  <div className="text-body-sm text-on-surface-variant">Messages</div>
                </div>
                <div>
                  <div className="text-h3 font-bold text-secondary">{villaSyncResult.apartments_found}</div>
                  <div className="text-body-sm text-on-surface-variant">Apartments</div>
                </div>
                <div>
                  <div className="text-h3 font-bold text-tertiary">{villaSyncResult.new_villas_created}</div>
                  <div className="text-body-sm text-on-surface-variant">Created</div>
                </div>
                <div>
                  <div className="text-h3 font-bold text-outline">{villaSyncResult.villas_updated}</div>
                  <div className="text-body-sm text-on-surface-variant">Updated</div>
                </div>
                <div>
                  <div className="text-h3 font-bold text-error">{villaSyncResult.villas_marked_rented}</div>
                  <div className="text-body-sm text-on-surface-variant">Rented</div>
                </div>
              </div>

              {villaSyncResult.errors.length > 0 && (
                <div className="border-error-container bg-error-container/20 rounded-lg border p-sm">
                  <p className="text-body-sm font-semibold text-error mb-xs">Errors ({villaSyncResult.errors.length}):</p>
                  <ul className="list-disc pl-md text-body-sm text-error">
                    {villaSyncResult.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Progress bar during streaming */}
      {isStreaming && progress && (
        <div className="border-outline-variant bg-surface-container-low rounded-xl border p-md">
          <h3 className="text-h4 font-semibold text-on-surface mb-sm">Đang xử lý...</h3>
          <div className="mb-sm flex items-center gap-md">
            <div className="bg-surface-container-high h-2 flex-1 overflow-hidden rounded-full">
              <div
                className="bg-primary h-full rounded-full transition-all duration-300"
                style={{ width: `${Math.round((progress.completed / progress.total) * 100)}%` }}
              />
            </div>
            <span className="text-body-sm text-on-surface-variant shrink-0">
              {progress.completed}/{progress.total}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-md text-center text-body-sm">
            <div>
              <span className="text-secondary font-semibold">{progress.extracted}</span>
              <span className="text-on-surface-variant ml-1">Extracted</span>
            </div>
            <div>
              <span className="text-outline font-semibold">{progress.not_listing}</span>
              <span className="text-on-surface-variant ml-1">Non-BĐS</span>
            </div>
            <div>
              <span className="text-error font-semibold">{progress.failed}</span>
              <span className="text-on-surface-variant ml-1">Lỗi</span>
            </div>
          </div>
        </div>
      )}

      {/* Results Summary */}
      {summary && (
        <div className="border-outline-variant bg-surface-container-low rounded-xl border p-md">
          <h3 className="text-h4 font-semibold text-on-surface mb-sm">Kết quả</h3>
          <div className="grid grid-cols-4 gap-md text-center">
            <div>
              <div className="text-h3 font-bold text-primary">{summary.total}</div>
              <div className="text-body-sm text-on-surface-variant">Tổng</div>
            </div>
            <div>
              <div className="text-h3 font-bold text-secondary">{summary.extracted}</div>
              <div className="text-body-sm text-on-surface-variant">Extract được</div>
            </div>
            <div>
              <div className="text-h3 font-bold text-outline">{summary.not_listing}</div>
              <div className="text-body-sm text-on-surface-variant">Không phải BĐS</div>
            </div>
            <div>
              <div className="text-h3 font-bold text-error">{summary.failed}</div>
              <div className="text-body-sm text-on-surface-variant">Lỗi</div>
            </div>
          </div>
        </div>
      )}

      {/* Results List */}
      {results && results.length > 0 && (
        <div className="flex flex-col gap-md">
          {results.map((item, idx) => (
            <ResultCard key={item.raw_message_id || idx} item={item} index={idx} />
          ))}
        </div>
      )}

      {/* ── Preview Section (after test results) ────────────────────── */}
      {results && results.length > 0 && (
        <div className="flex flex-col gap-lg border-t border-outline-variant pt-lg mt-lg">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-h4 font-semibold text-on-surface">
                Bản xem trước (chưa gửi GoDaNang)
              </h3>
              <p className="text-body-sm text-on-surface-variant">
                Xem payload chính xác sẽ gửi lên GoDaNang. Chọn listing muốn sync và bấm "Gửi".
              </p>
            </div>
            {!previewData && (
              <button
                type="button"
                onClick={handleCreatePreview}
                disabled={previewLoading || !lastTestRequest}
                className="bg-tertiary text-on-tertiary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
              >
                {previewLoading ? "Đang tạo..." : "🔍 Tạo bản xem trước"}
              </button>
            )}
          </div>

          {previewError && (
            <div className="border-error-container bg-error-container/40 rounded-xl border px-md py-sm text-body-sm text-error">
              {previewError}
            </div>
          )}

          {previewData && previewData.listings.length > 0 && (
            <>
              {/* Summary bar */}
              <div className="flex gap-md text-body-sm">
                <span>
                  Chèn mới: <strong className="text-success">{previewData.would_insert}</strong>
                </span>
                <span>
                  Cập nhật: <strong className="text-warning">{previewData.would_update}</strong>
                </span>
                <span>
                  Bỏ qua: <strong className="text-on-surface-variant">{previewData.would_skip}</strong>
                </span>
              </div>

              {/* Listing cards */}
              <div className="flex flex-col gap-md">
                {previewData.listings.map((listing, idx) => (
                  <PreviewCard
                    key={listing.raw_message_id || idx}
                    listing={listing}
                    selected={selectedIds.has(listing.raw_message_id)}
                    synced={syncedIds.has(listing.raw_message_id)}
                    syncing={previewSyncLoading}
                    onToggle={() => {
                      setSelectedIds((prev) => {
                        const next = new Set(prev);
                        if (next.has(listing.raw_message_id)) {
                          next.delete(listing.raw_message_id);
                        } else {
                          next.add(listing.raw_message_id);
                        }
                        return next;
                      });
                    }}
                  />
                ))}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between border-t border-outline-variant pt-md">
                <span className="text-body-sm text-on-surface-variant">
                  Đã chọn {selectedIds.size} / {previewData.listings.length} listing
                </span>
                <button
                  type="button"
                  onClick={handleSendSelected}
                  disabled={selectedIds.size === 0 || previewSyncLoading}
                  className="bg-primary text-on-primary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
                >
                  {previewSyncLoading
                    ? "Đang gửi..."
                    : `Gửi ${selectedIds.size} cái đã chọn`}
                </button>
              </div>
            </>
          )}

          {previewData && previewData.listings.length === 0 && (
            <div className="text-body-sm text-on-surface-variant py-md">
              Không có listing nào để xem trước.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResultCard({ item, index }: { item: AgentTestExtractResult; index: number }) {
  const statusColors: Record<string, string> = {
    extracted: "border-secondary-container bg-secondary-container/20",
    not_listing: "border-outline-variant bg-surface-container-low",
    failed: "border-error-container bg-error-container/20",
  };
  const statusLabels: Record<string, string> = {
    extracted: "✅ Extracted",
    not_listing: "ℹ️ Không phải BĐS",
    failed: "❌ Lỗi",
  };

  return (
    <div className={`rounded-xl border p-md ${statusColors[item.status] || ""}`}>
      <div className="flex items-center justify-between mb-sm">
        <div className="flex items-center gap-sm">
          <span className="text-body-sm font-medium text-on-surface">
            #{index + 1} — {item.raw_message_id}
          </span>
          {item.source_message_ids.length > 1 && (
            <span className="rounded bg-tertiary-container px-2 py-0.5 text-label-sm text-on-tertiary-container">
              Ghép từ {item.source_message_ids.length} tin nhắn
            </span>
          )}
        </div>
        <span className="text-body-sm font-semibold">{statusLabels[item.status]}</span>
      </div>

      {item.raw_text && (
        <p className="text-body-sm text-on-surface-variant mb-sm line-clamp-2">
          {item.raw_text}
        </p>
      )}

      {item.error_message && (
        <p className="text-body-sm text-error mb-sm">{item.error_message}</p>
      )}

      {item.listing && (
        <div className="grid grid-cols-2 gap-sm text-body-sm md:grid-cols-3">
          <Field label="Tên" value={item.listing.apartment_name} />
          <Field label="Quận" value={item.listing.district} />
          <Field label="Phòng ngủ" value={item.listing.bedrooms} />
          <Field
            label="Giá"
            value={
              item.listing.price_vnd
                ? `${(item.listing.price_vnd / 1_000_000).toFixed(1)}tr`
                : null
            }
          />
          <Field
            label="Diện tích"
            value={item.listing.area_m2 ? `${item.listing.area_m2}m²` : null}
          />
          <Field label="SĐT" value={item.listing.contact_phone} />
          <Field
            label="Ảnh"
            value={
              item.listing.image_count > 0
                ? `${item.listing.image_count} ảnh`
                : "0"
            }
          />
        </div>
      )}

      {item.listing && item.listing.images.length > 0 ? (
        <div className="mt-sm flex flex-wrap gap-xs">
          {item.listing.images.slice(0, 8).map((url, i) => (
            // Plain <img> is used here on purpose: the agent test result is
            // a transient preview of arbitrary Supabase Storage URLs, and
            // we don't want next/image's optimization roundtrip to mask
            // broken URLs with fallback placeholders. The next.config.js
            // remotePatterns allowlist covers these origins.
            <a
              key={`${item.raw_message_id}-img-${i}`}
              href={url}
              target="_blank"
              rel="noreferrer"
              className="border-outline-variant bg-surface-container-lowest hover:border-primary block h-16 w-16 overflow-hidden rounded-md border transition"
              title={url}
            >
              <img
                src={url}
                alt={`Ảnh ${i + 1} của ${item.listing?.apartment_name ?? "listing"}`}
                className="h-full w-full object-cover"
                loading="lazy"
                onError={(e) => {
                  const target = e.currentTarget;
                  target.style.opacity = "0.3";
                }}
              />
            </a>
          ))}
          {item.listing.images.length > 8 ? (
            <span className="border-outline-variant text-on-surface-variant flex h-16 w-16 items-center justify-center rounded-md border text-xs font-semibold">
              +{item.listing.images.length - 8}
            </span>
          ) : null}
        </div>
      ) : item.listing && item.listing.image_count > 0 ? (
        <p className="text-body-xs text-on-surface-variant mt-xs italic">
          {item.listing.image_count} ảnh đính kèm (chưa hiển thị — kiểm tra zalo_message_assets)
        </p>
      ) : null}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div>
      <span className="text-on-surface-variant">{label}: </span>
      <span className="font-medium text-on-surface">{value}</span>
    </div>
  );
}

function PreviewCard({
  listing,
  selected,
  synced,
  syncing,
  onToggle,
}: {
  listing: AgentPreviewListing;
  selected: boolean;
  synced: boolean;
  syncing: boolean;
  onToggle: () => void;
}) {
  const badgeColor: Record<string, string> = {
    insert: "bg-success/15 text-success",
    update: "bg-warning/15 text-warning",
    skip: "bg-surface-container-high text-on-surface-variant",
  };
  const badgeLabel: Record<string, string> = {
    insert: "INSERT",
    update: "UPDATE",
    skip: "SKIP",
  };

  return (
    <div
      className={`rounded-xl border p-md transition ${
        synced
          ? "border-success bg-success/5 opacity-70"
          : selected
            ? "border-primary"
            : "border-outline-variant"
      }`}
    >
      <div className="flex items-start justify-between mb-sm">
        <div className="flex items-center gap-sm min-w-0">
          <span className="text-body-sm font-medium text-on-surface truncate">
            {listing.title || "(không tiêu đề)"}
          </span>
          {listing.source_message_ids.length > 1 && (
            <span className="rounded bg-tertiary-container px-2 py-0.5 text-label-sm text-on-tertiary-container shrink-0">
              Ghép từ {listing.source_message_ids.length} tin nhắn
            </span>
          )}
          <span
            className={`rounded-md px-sm py-0.5 text-body-xs font-semibold ${badgeColor[listing.operation] || ""}`}
          >
            {badgeLabel[listing.operation] || listing.operation}
          </span>
        </div>
        <div className="flex items-center gap-xs shrink-0 ml-sm">
          {synced ? (
            <span className="text-body-xs text-success font-semibold">✅ Đã gửi</span>
          ) : (
            <label className="flex items-center gap-xs cursor-pointer">
              <input
                type="checkbox"
                checked={selected}
                onChange={onToggle}
                disabled={syncing}
                className="accent-primary"
              />
              <span className="text-body-sm text-on-surface-variant">Gửi</span>
            </label>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-sm text-body-sm mb-sm md:grid-cols-4">
        <Field label="Quận" value={listing.district} />
        <Field label="Phòng ngủ" value={listing.bedrooms} />
        <Field label="Giá" value={listing.price_vnd ? `${(listing.price_vnd / 1_000_000).toFixed(1)}tr` : null} />
        <Field label="Diện tích" value={listing.area_m2 ? `${listing.area_m2}m²` : null} />
      </div>

      <details className="text-body-xs">
        <summary className="text-on-surface-variant cursor-pointer hover:text-on-surface">Payload JSON</summary>
        <pre className="mt-xs bg-surface-container-high rounded-lg p-sm overflow-x-auto text-body-xs text-on-surface">
          {JSON.stringify(listing.payload, null, 2)}
        </pre>
      </details>
    </div>
  );
}
