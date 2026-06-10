"use client";

import { useCallback, useState } from "react";

import { testAgentExtract } from "@/services/zaloCrawlerService";
import type {
  AgentTestExtractResponse,
  AgentTestExtractResult,
} from "@/types/zalo-api";

type InputMode = "fake" | "text";

interface FakeGroup {
  group_name: string;
  messages: { id: string; text: string; images: string[] }[];
}

interface FakeDataResponse {
  groups: FakeGroup[];
  total_messages: number;
  total_images: number;
}

export function ZaloAgentTestPanel({ userId: _userId }: { userId: string }) {
  const [mode, setMode] = useState<InputMode>("fake");
  const [pasteText, setPasteText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AgentTestExtractResponse | null>(null);
  const [fakeData, setFakeData] = useState<FakeDataResponse | null>(null);
  const [selectedFakeGroup, setSelectedFakeGroup] = useState<string>("all");

  const handleGenerateFake = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);

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

      const data: FakeDataResponse = await res.json();
      setFakeData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi không xác định");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleTestFake = useCallback(async () => {
    if (!fakeData) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const groupsToTest =
        selectedFakeGroup === "all"
          ? fakeData.groups
          : fakeData.groups.filter((g) => g.group_name === selectedFakeGroup);

      const allTexts = groupsToTest.flatMap((g) => g.messages.map((m) => m.text));

      const res = await testAgentExtract({ texts: allTexts });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi không xác định");
    } finally {
      setLoading(false);
    }
  }, [fakeData, selectedFakeGroup]);

  const handleTestText = useCallback(async () => {
    const texts = pasteText
      .split("\n")
      .filter((t) => t.trim());

    if (texts.length === 0) {
      setError("Vui lòng nhập text");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await testAgentExtract({ texts });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi không xác định");
    } finally {
      setLoading(false);
    }
  }, [pasteText]);

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
                disabled={loading}
                className="bg-tertiary text-on-tertiary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
              >
                {loading ? "Đang tạo..." : "🎲 Tạo dữ liệu ảo để test Agent"}
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
                  disabled={loading}
                  className="bg-primary text-on-primary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50"
                >
                  {loading ? "Đang test..." : "🚀 Test Agent"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setFakeData(null);
                    setResult(null);
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
            disabled={loading}
            className="bg-primary text-on-primary rounded-xl px-lg py-sm text-body-md font-semibold transition hover:opacity-90 disabled:opacity-50 self-start"
          >
            {loading ? "Đang test..." : "🚀 Test Agent"}
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="border-error-container bg-error-container/40 rounded-xl border px-md py-sm text-body-sm text-error">
          {error}
        </div>
      )}

      {/* Results Summary */}
      {result && (
        <div className="border-outline-variant bg-surface-container-low rounded-xl border p-md">
          <h3 className="text-h4 font-semibold text-on-surface mb-sm">Kết quả</h3>
          <div className="grid grid-cols-4 gap-md text-center">
            <div>
              <div className="text-h3 font-bold text-primary">{result.total}</div>
              <div className="text-body-sm text-on-surface-variant">Tổng</div>
            </div>
            <div>
              <div className="text-h3 font-bold text-secondary">{result.extracted}</div>
              <div className="text-body-sm text-on-surface-variant">Extract được</div>
            </div>
            <div>
              <div className="text-h3 font-bold text-outline">{result.not_listing}</div>
              <div className="text-body-sm text-on-surface-variant">Không phải BĐS</div>
            </div>
            <div>
              <div className="text-h3 font-bold text-error">{result.failed}</div>
              <div className="text-body-sm text-on-surface-variant">Lỗi</div>
            </div>
          </div>
        </div>
      )}

      {/* Results List */}
      {result && result.results.length > 0 && (
        <div className="flex flex-col gap-md">
          {result.results.map((item, idx) => (
            <ResultCard key={item.raw_message_id || idx} item={item} index={idx} />
          ))}
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
        <span className="text-body-sm font-medium text-on-surface">
          #{index + 1} — {item.raw_message_id}
        </span>
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
          <Field label="Ảnh" value={`${item.listing.image_count} ảnh`} />
        </div>
      )}
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
