"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  addListGroupBulk,
  addN8nGroup,
  getAllN8nGroups,
  removeN8nGroup,
  updateN8nGroup,
} from "@/services/linkedinCrawlerService";
import { MaterialIcon } from "@/components/ui";

import type { ManagedGroupRow } from "@/lib/n8n-groups-normalize";
import { normalizeN8nGroupsList } from "@/lib/n8n-groups-normalize";
import { findDuplicateManagedGroup, groupUrlMatchKey } from "@/lib/group-duplicate-check";
import {
  appendCommaNewlineAfterTrailingGroupUrl,
  parseGroupUrlsFromBulkInput,
} from "@/lib/parse-group-urls-bulk";
import { cn } from "@/lib/utils";

import { useDashboard } from "./dashboard-context";

const GROUPS_PAGE_SIZE = 8;
/** Chờ backend + n8n (giây) — khớp .env / timeout server (~5–6 phút). */
const ADD_LIST_GROUP_WEBHOOK_TIMEOUT_SEC = 360;
/** Modal thành công sau thêm nhóm — tự đóng để không chặn thao tác. */
const ADD_SUCCESS_DISMISS_MS = 2000;

export function N8nManagedGroupsSection() {
  const d = useDashboard();
  const email = d.email.trim();

  const [rows, setRows] = useState<ManagedGroupRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [busyMutation, setBusyMutation] = useState(false);

  const [addOpen, setAddOpen] = useState(false);
  const [addUrl, setAddUrl] = useState("");
  const [addName, setAddName] = useState("");
  const [addMember, setAddMember] = useState("");

  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState("");

  /** Thông báo sau add thành công — tự đóng sau vài giây và gọi get-all (hoặc bấm OK sớm). */
  const [addSuccessMessage, setAddSuccessMessage] = useState<string | null>(null);

  const [editRow, setEditRow] = useState<ManagedGroupRow | null>(null);
  const [editNewUrl, setEditNewUrl] = useState("");
  const [editNewName, setEditNewName] = useState("");
  const [editNewMember, setEditNewMember] = useState("");

  const loadGroups = useCallback(async () => {
    if (!email) {
      setRows([]);
      return;
    }
    setLoading(true);
    setError(null);
    setInfo(null);
    try {
      const res = await getAllN8nGroups({ email });
      if (!res.success) {
        throw new Error(res.message || "Không lấy được danh sách nhóm.");
      }
      const list = normalizeN8nGroupsList(res.data?.groups ?? res.data?.parsed);
      setRows(list);
      setPage(1);
      const totalFromApi = typeof res.data?.total === "number" ? res.data.total : list.length;
      if (list.length === 0) {
        setInfo(
          "Webhook trả về nhưng không có dòng nhóm sau khi parse — kiểm tra JSON n8n (mảng hoặc { data/groups/rows }).",
        );
      } else {
        setInfo(`Đã tải ${list.length}/${totalFromApi} nhóm cho ${email}.`);
      }
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : "Lỗi tải danh sách nhóm.");
    } finally {
      setLoading(false);
    }
  }, [email]);

  useEffect(() => {
    if (email) void loadGroups();
  }, [email, d.dashboardReloadToken, loadGroups]);

  const totalPages = Math.max(1, Math.ceil(rows.length / GROUPS_PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = useMemo(() => {
    const start = (safePage - 1) * GROUPS_PAGE_SIZE;
    return rows.slice(start, start + GROUPS_PAGE_SIZE);
  }, [rows, safePage]);

  const bulkParsedUrls = useMemo(
    () => parseGroupUrlsFromBulkInput(bulkText),
    [bulkText],
  );

  const bulkDuplicateKeys = useMemo(() => {
    if (!rows.length) return new Set<string>();
    const keys = new Set<string>();
    for (const u of bulkParsedUrls) {
      if (findDuplicateManagedGroup(rows, u, email)) keys.add(groupUrlMatchKey(u));
    }
    return keys;
  }, [bulkParsedUrls, rows, email]);

  const bulkHasDuplicateInForm = bulkDuplicateKeys.size > 0;
  const bulkDuplicateUrls = useMemo(
    () => bulkParsedUrls.filter((u) => bulkDuplicateKeys.has(groupUrlMatchKey(u))),
    [bulkParsedUrls, bulkDuplicateKeys],
  );
  const bulkSubmitDisabled =
    busyMutation || bulkParsedUrls.length === 0 || bulkHasDuplicateInForm;

  const addUrlHasDuplicate = useMemo(() => {
    if (!addOpen || !email || !rows.length || !addUrl.trim()) return false;
    return Boolean(findDuplicateManagedGroup(rows, addUrl.trim(), email));
  }, [addOpen, email, rows, addUrl]);

  const openAdd = () => {
    setError(null);
    setAddUrl("");
    setAddName("");
    setAddMember("");
    setAddOpen(true);
  };

  const openBulkAdd = () => {
    setBulkText("");
    setError(null);
    setBulkOpen(true);
  };

  const handleBulkUrlsBlur = () => {
    setBulkText((t) => appendCommaNewlineAfterTrailingGroupUrl(t));
  };

  const dismissAddSuccessAndRefresh = useCallback(() => {
    setAddSuccessMessage(null);
    void loadGroups();
  }, [loadGroups]);

  useEffect(() => {
    if (!addSuccessMessage) return;
    const id = window.setTimeout(() => {
      dismissAddSuccessAndRefresh();
    }, ADD_SUCCESS_DISMISS_MS);
    return () => window.clearTimeout(id);
  }, [addSuccessMessage, dismissAddSuccessAndRefresh]);

  /** Banner «Đã tải … nhóm cho …» sau refresh — tự ẩn để không chiếm chỗ lâu. */
  useEffect(() => {
    if (!info || !info.includes("Đã tải") || !info.includes("nhóm cho")) return;
    const id = window.setTimeout(() => setInfo(null), ADD_SUCCESS_DISMISS_MS);
    return () => window.clearTimeout(id);
  }, [info]);

  const submitBulkAdd = async () => {
    if (!email) {
      setError("Cần email crawler.");
      return;
    }
    setError(null);
    const group_urls = parseGroupUrlsFromBulkInput(bulkText);
    if (group_urls.length === 0) {
      setError(
        "Chưa có URL nhóm hợp lệ. Mỗi dòng một link hoặc nhiều link cách nhau bởi dấu phẩy / xuống dòng (linkedin.com/groups/<id>).",
      );
      return;
    }
    if (rows.length > 0 && email && group_urls.some((u) => findDuplicateManagedGroup(rows, u, email))) {
      return;
    }
    setBusyMutation(true);
    setInfo(null);
    try {
      const res = await addListGroupBulk({
        group_urls,
        email,
        post_to_webhook: true,
        delay_min_sec: 2,
        delay_max_sec: 5,
        webhook_timeout_sec: ADD_LIST_GROUP_WEBHOOK_TIMEOUT_SEC,
      });
      if (!res.success) {
        throw new Error(res.message || "Thêm hàng loạt thất bại.");
      }
      const items = res.data?.items ?? [];
      const failed = items.filter((r) => !r.success);
      setBulkOpen(false);
      setBulkText("");
      const msg =
        failed.length > 0
          ? `${res.message}\n\n${failed.length}/${items.length} URL cào lỗi — kiểm tra session LinkedIn / URL.`
          : res.message || "Đã thêm nhóm hàng loạt thành công.";
      setAddSuccessMessage(msg);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Thêm hàng loạt thất bại.");
    } finally {
      setBusyMutation(false);
    }
  };

  const submitAdd = async () => {
    if (!email) {
      setError("Cần email crawler.");
      return;
    }
    const m = Number(addMember.replace(/\s/g, ""));
    if (!addUrl.trim() || !addName.trim() || addMember.trim() === "" || Number.isNaN(m) || m < 0) {
      setError("Điền đủ URL nhóm, tên nhóm và số thành viên (số ≥ 0).");
      return;
    }
    if (rows.length > 0 && findDuplicateManagedGroup(rows, addUrl.trim(), email)) {
      return;
    }
    setBusyMutation(true);
    setError(null);
    try {
      const res = await addN8nGroup({
        url_group: addUrl.trim(),
        name_group: addName.trim(),
        member: m,
        email,
      });
      if (!res.success) throw new Error(res.message || "Thêm nhóm thất bại.");
      setAddOpen(false);
      setAddSuccessMessage(res.message || "Đã thêm nhóm thành công.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Thêm nhóm thất bại.");
    } finally {
      setBusyMutation(false);
    }
  };

  const openEdit = (row: ManagedGroupRow) => {
    setEditRow(row);
    setEditNewUrl("");
    setEditNewName("");
    setEditNewMember("");
  };

  const submitEdit = async () => {
    if (!editRow || !email) return;
    setBusyMutation(true);
    setError(null);
    try {
      const payload: Parameters<typeof updateN8nGroup>[0] = {
        url_group_need_update: editRow.url_group,
        name_group: editRow.name_group,
        member: editRow.member,
        email,
      };
      if (editNewUrl.trim()) payload.new_url_group = editNewUrl.trim();
      if (editNewName.trim()) payload.new_name_group = editNewName.trim();
      if (editNewMember.trim()) {
        const n = Number(editNewMember.replace(/\s/g, ""));
        if (Number.isNaN(n) || n < 0) {
          throw new Error("Số thành viên mới không hợp lệ.");
        }
        payload.new_member = n;
      }
      const res = await updateN8nGroup(payload);
      if (!res.success) throw new Error(res.message || "Cập nhật thất bại.");
      setEditRow(null);
      await loadGroups();
      setInfo(res.message || "Đã cập nhật nhóm và làm mới danh sách.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Cập nhật thất bại.");
    } finally {
      setBusyMutation(false);
    }
  };

  const confirmRemove = async (row: ManagedGroupRow) => {
    if (!email) return;
    const ok = window.confirm(`Xóa nhóm khỏi n8n?\n${row.name_group}\n${row.url_group}`);
    if (!ok) return;
    setBusyMutation(true);
    setError(null);
    try {
      const res = await removeN8nGroup({
        url_group: row.url_group,
        email,
      });
      if (!res.success) throw new Error(res.message || "Xóa thất bại.");
      await loadGroups();
      setInfo(res.message || "Đã xóa nhóm và làm mới danh sách.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Xóa thất bại.");
    } finally {
      setBusyMutation(false);
    }
  };

  return (
    <section className="border-outline-variant bg-surface-container-lowest mb-xl rounded-xl border p-lg shadow-sm">
      <div className="mb-lg flex flex-col justify-between gap-md md:flex-row md:items-center">
        <div>
          <h2 className="text-h2 text-on-surface font-semibold">
            Nhóm cào
          </h2>
          
        </div>
        <div className="flex flex-wrap gap-sm">
          <button
            type="button"
            className="bg-primary text-on-primary hover:bg-primary-container flex items-center gap-2 rounded-lg px-md py-sm text-xs font-bold uppercase tracking-wide disabled:opacity-50"
            onClick={() => void loadGroups()}
            disabled={loading || !email}
          >
            <MaterialIcon name="refresh" className="shrink-0 text-[18px]" />
            {loading ? "Đang tải…" : "Tải lại danh sách"}
          </button>
          <button
            type="button"
            className="border-outline-variant bg-secondary-container/30 text-on-secondary-container flex items-center gap-2 rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide disabled:opacity-50"
            onClick={openBulkAdd}
            disabled={!email || busyMutation}
          >
            <MaterialIcon name="playlist_add" className="shrink-0 text-[18px]" />
            Thêm hàng loạt
          </button>
          <button
            type="button"
            className="border-outline-variant bg-surface flex items-center gap-2 rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide disabled:opacity-50"
            onClick={openAdd}
            disabled={!email || busyMutation}
          >
            <MaterialIcon name="add" className="shrink-0 text-[18px]" />
            Thêm nhóm
          </button>
        </div>
      </div>

      {!email ? (
        <div
          className="border-outline-variant bg-surface-container-low rounded-lg border border-dashed px-md py-lg text-body-sm text-on-surface-variant"
          role="status"
        >
          Nhập email LinkedIn trên trang <strong className="text-on-surface">Crawler trực tiếp</strong> rồi quay lại
          để tải danh sách nhóm.
        </div>
      ) : null}

      {error ? (
        <div
          className="border-error-container bg-error-container/40 text-error mb-md rounded-lg border px-md py-sm text-body-sm"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {info && !error ? (
        <div
          className="border-secondary-container bg-secondary-container/20 text-on-secondary-container mb-md rounded-lg border px-md py-sm text-body-sm"
          role="status"
        >
          {info}
        </div>
      ) : null}

      {email && loading && rows.length === 0 ? (
        <p className="text-body-sm text-on-surface-variant py-lg text-center">Đang tải dữ liệu nhóm…</p>
      ) : null}

      {email && !loading && rows.length === 0 && !error ? (
        <div className="border-outline-variant bg-surface-container-low rounded-xl border border-dashed px-lg py-xl text-center">
          <p className="text-body-md text-on-surface font-semibold">Chưa có dòng nhóm</p>
          <p className="text-body-sm text-on-surface-variant mt-xs">
            Bấm «Tải lại danh sách» hoặc «Thêm nhóm» sau khi cấu hình webhook{" "}
            <code className="text-xs">N8N_WEBHOOK_GET_GROUP</code>.
          </p>
        </div>
      ) : null}

      {rows.length > 0 ? (
        <>
          <div className="overflow-x-auto rounded-lg border border-outline-variant">
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <thead className="bg-surface-container-low border-outline-variant border-b">
                <tr>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    STT
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    URL nhóm
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md font-semibold uppercase">
                    Tên nhóm
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md text-right font-semibold uppercase">
                    Thành viên
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-md text-right font-semibold uppercase">
                    Thao tác
                  </th>
                </tr>
              </thead>
              <tbody className="divide-outline-variant divide-y">
                {pageRows.map((row, idx) => (
                  <tr key={`${row.url_group}-${idx}`} className="hover:bg-surface-container/50">
                    <td className="text-on-surface-variant px-md py-md tabular-nums">
                      {row.row_number ?? (safePage - 1) * GROUPS_PAGE_SIZE + idx + 1}
                    </td>
                    <td className="max-w-[280px] px-md py-md">
                      <a
                        href={row.url_group}
                        target="_blank"
                        rel="noreferrer"
                        className="text-primary break-all font-medium hover:underline"
                      >
                        {row.url_group}
                      </a>
                    </td>
                    <td className="text-on-surface max-w-[200px] px-md py-md">
                      <span className="line-clamp-2" title={row.name_group}>
                        {row.name_group}
                      </span>
                    </td>
                    <td className="text-on-surface px-md py-md text-right tabular-nums">
                      {row.member.toLocaleString("vi-VN")}
                    </td>
                    <td className="px-md py-md text-right">
                      <div className="flex flex-wrap items-center justify-end gap-1">
                        <button
                          type="button"
                          className="text-on-surface-variant hover:text-primary rounded p-1.5 transition-colors"
                          title="Sửa nhóm"
                          onClick={() => openEdit(row)}
                          disabled={busyMutation}
                          aria-label={`Sửa ${row.name_group}`}
                        >
                          <MaterialIcon name="edit" className="text-[20px]" />
                        </button>
                        <button
                          type="button"
                          className="text-on-surface-variant hover:text-error rounded p-1.5 transition-colors"
                          title="Xóa nhóm"
                          onClick={() => void confirmRemove(row)}
                          disabled={busyMutation}
                          aria-label={`Xóa ${row.name_group}`}
                        >
                          <MaterialIcon name="delete" className="text-[20px]" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="text-body-sm text-on-surface-variant mt-lg flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <span>
              Trang {safePage}/{totalPages} — {rows.length} nhóm
            </span>
            <div className="flex items-center gap-base">
              <button
                type="button"
                className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={safePage <= 1}
                aria-label="Trang trước"
              >
                <MaterialIcon name="chevron_left" />
              </button>
              <span className="text-on-surface px-md font-bold">{safePage}</span>
              <button
                type="button"
                className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
                aria-label="Trang sau"
              >
                <MaterialIcon name="chevron_right" />
              </button>
            </div>
          </div>
        </>
      ) : null}

      {bulkOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center p-md sm:items-center"
          role="presentation"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45 backdrop-blur-[1px]"
            aria-label="Đóng"
            onClick={() => !busyMutation && setBulkOpen(false)}
          />
          <div
            className="border-outline-variant bg-surface relative z-10 w-[min(92vw,720px)] rounded-xl border p-lg shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="bulk-add-group-title"
          >
            <h3 id="bulk-add-group-title" className="text-h3 text-on-surface font-semibold">
              Thêm nhóm hàng loạt
            </h3>
            <p className="text-body-sm text-on-surface-variant mt-sm">
              Dán URL nhóm (mỗi dòng một link, hoặc cách nhau bởi dấu phẩy). Khi rời ô nhập, hệ thống có thể tự thêm
              dấu phẩy và xuống dòng sau link cuối để dán tiếp. Quá trình cào + chờ n8n có thể mất vài phút — không đóng
              trang.
            </p>
            <div className="mt-md">
              <label
                htmlFor="bulk-group-urls"
                className="text-label-md text-on-surface-variant font-semibold uppercase"
              >
                Danh sách URL
              </label>
              <textarea
                id="bulk-group-urls"
                className="border-outline-variant bg-surface focus:border-primary mt-1 min-h-[200px] w-full resize-y rounded-lg border px-md py-sm font-mono text-sm"
                value={bulkText}
                onChange={(e) => {
                  setBulkText(e.target.value);
                  setError(null);
                }}
                onBlur={handleBulkUrlsBlur}
                placeholder={
                  "https://www.linkedin.com/groups/52007/\nhttps://www.linkedin.com/groups/6610234/"
                }
                spellCheck={false}
                disabled={busyMutation}
              />
              {bulkHasDuplicateInForm ? (
                <div className="border-outline-variant/80 bg-surface-container-low/60 mt-sm rounded-lg border p-sm">
                  <p className="text-label-md text-on-surface-variant mb-xs font-semibold uppercase">
                    URL trùng
                  </p>
                  <ul className="max-h-40 space-y-1 overflow-y-auto">
                    {bulkDuplicateUrls.map((u, idx) => (
                      <li
                        key={`dup-${groupUrlMatchKey(u)}-${idx}`}
                        className="break-all font-mono text-xs font-semibold leading-snug text-error"
                      >
                        {u}
                      </li>
                    ))}
                  </ul>
                  <p className="mt-sm text-xs text-error" role="status">
                    Nhóm đã có trong danh sách.
                  </p>
                </div>
              ) : null}
              {bulkParsedUrls.length > 0 ? (
                <p className="text-body-sm text-on-surface-variant mt-xs">
                  Đã nhận diện:{" "}
                  <strong className="text-on-surface">{bulkParsedUrls.length}</strong> URL hợp lệ
                </p>
              ) : null}
            </div>
            <div className="mt-lg flex justify-end gap-sm">
              <button
                type="button"
                className="rounded-lg px-md py-sm text-sm font-bold uppercase text-on-surface-variant"
                onClick={() => setBulkOpen(false)}
                disabled={busyMutation}
              >
                Hủy
              </button>
              <button
                type="button"
                className="bg-primary text-on-primary rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:opacity-50"
                onClick={() => void submitBulkAdd()}
                disabled={bulkSubmitDisabled}
              >
                {busyMutation ? "Đang lấy thông tin..." : "Thêm hàng loạt"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {addOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center p-md sm:items-center"
          role="presentation"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45 backdrop-blur-[1px]"
            aria-label="Đóng"
            onClick={() => !busyMutation && setAddOpen(false)}
          />
          <div
            className="border-outline-variant bg-surface relative z-10 w-[min(92vw,640px)] rounded-xl border p-lg shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-group-title"
          >
            <h3 id="add-group-title" className="text-h3 text-on-surface font-semibold">
              Thêm nhóm
            </h3>
            <div className="mt-md flex flex-col gap-base">
              <div>
                <label className="text-label-md text-on-surface-variant font-semibold uppercase">URL nhóm</label>
                <input
                  className={cn(
                    "bg-surface mt-1 w-full rounded-lg border px-md py-sm",
                    addUrlHasDuplicate
                      ? "border-error font-semibold text-error focus:border-error"
                      : "border-outline-variant focus:border-primary",
                  )}
                  value={addUrl}
                  onChange={(e) => {
                    setAddUrl(e.target.value);
                    setError(null);
                  }}
                  placeholder="https://www.linkedin.com/groups/…"
                />
                {addUrlHasDuplicate ? (
                  <p className="mt-xs text-xs text-error" role="status">
                    Nhóm đã có trong danh sách.
                  </p>
                ) : null}
              </div>
              <div>
                <label className="text-label-md text-on-surface-variant font-semibold uppercase">Tên nhóm</label>
                <input
                  className="border-outline-variant bg-surface focus:border-primary mt-1 w-full rounded-lg border px-md py-sm"
                  value={addName}
                  onChange={(e) => setAddName(e.target.value)}
                />
              </div>
              <div>
                <label className="text-label-md text-on-surface-variant font-semibold uppercase">Số thành viên</label>
                <input
                  type="number"
                  min={0}
                  className="border-outline-variant bg-surface focus:border-primary mt-1 w-full rounded-lg border px-md py-sm"
                  value={addMember}
                  onChange={(e) => setAddMember(e.target.value)}
                />
              </div>
            </div>
            <div className="mt-lg flex justify-end gap-sm">
              <button
                type="button"
                className="rounded-lg px-md py-sm text-sm font-bold uppercase text-on-surface-variant"
                onClick={() => setAddOpen(false)}
                disabled={busyMutation}
              >
                Hủy
              </button>
              <button
                type="button"
                className="bg-primary text-on-primary rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:opacity-50"
                onClick={() => void submitAdd()}
                disabled={busyMutation || addUrlHasDuplicate}
              >
                {busyMutation ? "Đang gửi…" : "Thêm"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {editRow ? (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center p-md sm:items-center"
          role="presentation"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45 backdrop-blur-[1px]"
            aria-label="Đóng"
            onClick={() => !busyMutation && setEditRow(null)}
          />
          <div
            className="border-outline-variant bg-surface relative z-10 w-[min(92vw,640px)] rounded-xl border p-lg shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-group-title"
          >
            <h3 id="edit-group-title" className="text-h3 text-on-surface font-semibold">
              Cập nhật nhóm
            </h3>
            <p className="text-body-sm text-on-surface-variant mt-sm">
              Hiện tại: <span className="font-medium text-on-surface">{editRow.name_group}</span> —{" "}
              {editRow.member.toLocaleString("vi-VN")} thành viên. Để trống các ô bên dưới nếu giữ nguyên (backend gửi
              giá trị cũ).
            </p>
            <div className="mt-md flex flex-col gap-base">
              <div>
                <label className="text-label-md text-on-surface-variant font-semibold uppercase">URL mới (tuỳ chọn)</label>
                <input
                  className="border-outline-variant bg-surface focus:border-primary mt-1 w-full rounded-lg border px-md py-sm"
                  value={editNewUrl}
                  onChange={(e) => setEditNewUrl(e.target.value)}
                  placeholder={editRow.url_group}
                />
              </div>
              <div>
                <label className="text-label-md text-on-surface-variant font-semibold uppercase">Tên mới (tuỳ chọn)</label>
                <input
                  className="border-outline-variant bg-surface focus:border-primary mt-1 w-full rounded-lg border px-md py-sm"
                  value={editNewName}
                  onChange={(e) => setEditNewName(e.target.value)}
                  placeholder={editRow.name_group}
                />
              </div>
              <div>
                <label className="text-label-md text-on-surface-variant font-semibold uppercase">Thành viên mới (tuỳ chọn)</label>
                <input
                  type="number"
                  min={0}
                  className="border-outline-variant bg-surface focus:border-primary mt-1 w-full rounded-lg border px-md py-sm"
                  value={editNewMember}
                  onChange={(e) => setEditNewMember(e.target.value)}
                  placeholder={String(editRow.member)}
                />
              </div>
            </div>
            <div className="mt-lg flex justify-end gap-sm">
              <button
                type="button"
                className="rounded-lg px-md py-sm text-sm font-bold uppercase text-on-surface-variant"
                onClick={() => setEditRow(null)}
                disabled={busyMutation}
              >
                Hủy
              </button>
              <button
                type="button"
                className="bg-primary text-on-primary rounded-lg px-lg py-sm text-sm font-bold uppercase disabled:opacity-50"
                onClick={() => void submitEdit()}
                disabled={busyMutation}
              >
                {busyMutation ? "Đang gửi…" : "Cập nhật"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {addSuccessMessage ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-md"
          role="dialog"
          aria-modal="true"
          aria-labelledby="add-success-title"
          aria-describedby="add-success-desc"
        >
          <div className="border-outline-variant bg-surface w-[min(92vw,440px)] rounded-xl border p-lg shadow-xl">
            <div className="flex items-start gap-md">
              <MaterialIcon name="check_circle" className="text-primary shrink-0 text-[40px]" filled />
              <div className="min-w-0 flex-1">
                <h3 id="add-success-title" className="text-h3 text-on-surface font-semibold">
                  Thành công
                </h3>
                <p
                  id="add-success-desc"
                  className="text-body-md text-on-surface mt-sm whitespace-pre-line break-words"
                >
                  {addSuccessMessage.trim() || "Các group đã được thêm thành công."}
                </p>
              </div>
            </div>
            <div className="mt-lg flex justify-end">
              <button
                type="button"
                className="bg-primary text-on-primary rounded-lg px-lg py-sm text-sm font-bold uppercase"
                onClick={() => void dismissAddSuccessAndRefresh()}
              >
                OK
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
