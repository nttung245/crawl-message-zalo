"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { MaterialIcon } from "@/components/ui";
import type { CrawlSessionGroup } from "@/types/api";

import {
  formatSheetCommentAutomationLabelVi,
  formatSheetInteractionLabelVi,
} from "./post-sheet-engagement";
import {
  enrichPostRowNumberIfMissing,
  pickNum,
  pickStr,
} from "./n8n-sheet-helpers";
import { SessionPostDetailModal } from "./SessionPostDetailModal";

function rowPatchKey(sessionId: string, rowNum: number): string {
  return `${sessionId}:${rowNum}`;
}

export interface SessionPostsModalProps {
  session: CrawlSessionGroup | null;
  titleSuffix?: string;
  onClose: () => void;
  dashboardEmail?: string | null;
  linkedinPlaywrightSessionId?: string | null;
  /** Sau reaction + webhook OK — dialog OK gọi (get-all-posts). */
  onRefreshSessions?: () => Promise<void>;
  refreshSessionsBusy?: boolean;
}

function ExternalLink({
  href,
  children,
}: {
  href: string;
  children: string;
}) {
  const ok = /^https?:\/\//i.test(href);
  if (!ok)
    return <span className="text-on-surface-variant break-all">{children}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary hover:underline break-all"
    >
      {children}
    </a>
  );
}

export function SessionPostsModal({
  session,
  titleSuffix = "",
  onClose,
  dashboardEmail = null,
  linkedinPlaywrightSessionId = null,
  onRefreshSessions,
  refreshSessionsBusy = false,
}: SessionPostsModalProps) {
  const PAGE_SIZE = 8;
  const [page, setPage] = useState(1);
  const [detailPost, setDetailPost] = useState<{
    raw: Record<string, unknown>;
    rowNum: number;
  } | null>(null);
  const [postPatches, setPostPatches] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const posts = useMemo(() => session?.posts ?? [], [session]);

  useEffect(() => {
    setPostPatches({});
  }, [session?.id_session_crawl]);

  const mergedPost = useCallback(
    (raw: Record<string, unknown>, rowNum: number): Record<string, unknown> => {
      const sid = session?.id_session_crawl ?? "";
      const patch = postPatches[rowPatchKey(sid, rowNum)];
      const base = patch ? { ...raw, ...patch } : raw;
      return enrichPostRowNumberIfMissing(base, rowNum);
    },
    [postPatches, session?.id_session_crawl],
  );

  useEffect(() => {
    if (!session) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (detailPost) setDetailPost(null);
      else onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [session, detailPost, onClose]);

  const totalPosts = posts.length;
  const totalPages = Math.max(1, Math.ceil(totalPosts / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const paginatedPosts = useMemo(
    () => posts.slice(pageStart, pageStart + PAGE_SIZE),
    [posts, pageStart],
  );
  if (!session) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center p-md sm:items-center"
      role="presentation"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/45 backdrop-blur-[1px]"
        aria-label="Đóng"
        onClick={onClose}
      />
      <div
        className="border-outline-variant bg-surface relative z-10 flex max-h-[min(90vh,880px)] w-full max-w-5xl flex-col rounded-xl border shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-modal-title"
      >
        <div className="border-outline-variant flex shrink-0 items-start justify-between gap-md border-b px-lg py-md">
          <div className="min-w-0">
            <h3
              id="session-modal-title"
              className="text-h3 text-on-surface font-semibold"
            >
              Chi tiết phiên cào
              {titleSuffix ? (
                <span className="text-on-surface-variant font-normal">
                  {" "}
                  {titleSuffix}
                </span>
              ) : null}
            </h3>
            <p className="text-body-sm text-on-surface-variant mt-1 break-all font-mono">
              {session.id_session_crawl}
            </p>
            <p className="text-body-sm text-on-surface-variant mt-0.5">
              Email:{" "}
              <span className="text-on-surface">
                {session.email_crawl || "—"}
              </span>
              {" · "}
              <span className="text-on-surface">
                {session.posts_count.toLocaleString("vi-VN")}
              </span>{" "}
              nhóm / bài trong phiên
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded-lg p-2 transition-colors"
            aria-label="Đóng hộp thoại"
          >
            <MaterialIcon name="close" className="text-[22px]" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-lg py-md">
          <div className="overflow-x-auto rounded-lg border border-outline-variant">
            <table className="w-full min-w-[960px] border-collapse text-left text-sm">
              <thead className="bg-surface-container-low border-outline-variant border-b">
                <tr>
                  <th className="text-table-header text-on-surface-variant px-md py-sm font-semibold uppercase">
                    #
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm font-semibold uppercase">
                    Nhóm
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm font-semibold uppercase">
                    Link nhóm
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm font-semibold uppercase">
                    Link bài
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm font-semibold uppercase">
                    Tác giả
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm text-right font-semibold uppercase">
                    Like
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm text-right font-semibold uppercase">
                    CMT
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm text-right font-semibold uppercase">
                    Điểm
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm font-semibold uppercase">
                    Ngày
                  </th>
                  <th className="text-table-header text-on-surface-variant px-md py-sm text-right font-semibold uppercase">
                    Chi tiết
                  </th>
                </tr>
              </thead>
              <tbody className="divide-outline-variant divide-y">
                {paginatedPosts.map((raw, idx) => {
                  const rowNum = pageStart + idx + 1;
                  const post = mergedPost(raw as Record<string, unknown>, rowNum);
                  const interactLabel = formatSheetInteractionLabelVi(post);
                  const commentDoneLabel =
                    formatSheetCommentAutomationLabelVi(post);
                  const groupName = pickStr(post, [
                    "Tên nhóm",
                    "group_name",
                    "groupName",
                  ]);
                  const groupUrl = pickStr(post, [
                    "URL_Nhóm",
                    "URL_nhom",
                    "group_url",
                    "groupUrl",
                  ]);
                  const postUrl = pickStr(post, [
                    "URL_Bài_Viết",
                    "post_url",
                    "postUrl",
                  ]);
                  const author = pickStr(post, ["Tác giả", "author"]);
                  const likes = pickNum(post, ["Số like", "likes"]);
                  const comments = pickNum(post, ["Số comment", "comments"]);
                  const score = pickNum(post, ["Điểm", "score", "Score"]);
                  const day = pickStr(post, ["Ngày", "date"]).slice(0, 10);
                  return (
                    <tr key={idx} className="hover:bg-surface-container/60">
                      <td className="text-on-surface-variant px-md py-sm">
                        {rowNum}
                      </td>
                      <td className="text-on-surface max-w-[140px] px-md py-sm">
                        <span className="line-clamp-2" title={groupName}>
                          {groupName || "—"}
                        </span>
                      </td>
                      <td className="max-w-[140px] px-md py-sm align-top">
                        {groupUrl ? (
                          <ExternalLink href={groupUrl}>Mở</ExternalLink>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="max-w-[160px] px-md py-sm align-top">
                        {postUrl ? (
                          <ExternalLink href={postUrl}>Mở</ExternalLink>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="text-on-surface max-w-[120px] px-md py-sm">
                        <span className="line-clamp-2" title={author}>
                          {author || "—"}
                        </span>
                      </td>
                      <td className="text-on-surface px-md py-sm text-right tabular-nums">
                        {likes.toLocaleString("vi-VN")}
                      </td>
                      <td className="text-on-surface px-md py-sm text-right tabular-nums">
                        {comments.toLocaleString("vi-VN")}
                      </td>
                      <td className="text-on-surface px-md py-sm text-right tabular-nums">
                        {score.toLocaleString("vi-VN")}
                      </td>
                      <td className="text-on-surface-variant px-md py-sm whitespace-nowrap">
                        {day || "—"}
                      </td>
                      <td className="max-w-[200px] px-md py-sm text-right align-middle">
                        <div className="flex flex-wrap items-center justify-end gap-x-sm gap-y-1">
                          <span
                            className="text-on-surface block min-w-0 max-w-[92px] break-words text-right text-[10px] leading-tight font-semibold"
                            title="Sheet: reaction"
                          >
                            {interactLabel}
                          </span>
                          <span
                            className="text-on-surface block min-w-0 max-w-[92px] break-words text-right text-[10px] leading-tight font-semibold"
                            title="Sheet: comment (automation)"
                          >
                            {commentDoneLabel}
                          </span>
                          <button
                            type="button"
                            onClick={() =>
                              setDetailPost({
                                raw: post,
                                rowNum,
                              })
                            }
                            className="border-primary text-primary hover:bg-primary/5 inline-flex shrink-0 items-center gap-1 rounded-lg border bg-transparent px-sm py-1.5 text-[11px] font-bold uppercase tracking-wide"
                          >
                            <MaterialIcon
                              name="visibility"
                              className="text-[16px]"
                            />
                            Xem chi tiết
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="text-body-sm text-on-surface-variant mt-md flex items-center justify-between gap-md">
            <span>
              Hiển thị {pageStart + 1}–
              {Math.min(pageStart + PAGE_SIZE, totalPosts)} / {totalPosts} bài
            </span>
            <div className="flex items-center gap-sm">
              <button
                type="button"
                className="hover:bg-surface-container-high rounded p-2 transition-colors disabled:opacity-30"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={safePage <= 1}
                aria-label="Trang trước"
              >
                <MaterialIcon name="chevron_left" />
              </button>
              <span className="text-on-surface px-md font-bold">
                {safePage}/{totalPages}
              </span>
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
        </div>
      </div>

      {detailPost ? (
        <SessionPostDetailModal
          session={session}
          post={detailPost.raw}
          rowNumber={detailPost.rowNum}
          titleSuffix={titleSuffix}
          dashboardEmail={dashboardEmail}
          linkedinPlaywrightSessionId={linkedinPlaywrightSessionId}
          onRefreshSessions={onRefreshSessions}
          refreshSessionsBusy={refreshSessionsBusy}
          onReactionSucceeded={(rowNum, patch) => {
            const key = rowPatchKey(session.id_session_crawl, rowNum);
            setPostPatches((prev) => ({
              ...prev,
              [key]: { ...prev[key], ...patch },
            }));
            setDetailPost((d) =>
              d && d.rowNum === rowNum
                ? { ...d, raw: { ...d.raw, ...patch } }
                : d,
            );
          }}
          onClose={() => setDetailPost(null)}
        />
      ) : null}
    </div>
  );
}
