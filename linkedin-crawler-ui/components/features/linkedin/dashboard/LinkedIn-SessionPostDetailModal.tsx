"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { MaterialIcon, type MaterialSymbolName } from "@/components/ui";
import { useLinkedInEngagementQueue } from "@/components/features/linkedin/dashboard/linkedin-engagement-queue-context";
import {
  parseAppCommentsFromPost,
  appCommentContent,
  appCommentDay,
} from "@/lib/LinkedIn-appComments";
import { readLinkedInCredentials } from "@/lib/credentials";
import { syncPostProgress } from "@/services/linkedinCrawlerService";
import { resolveProfileSlugFromSheetForEmail } from "@/lib/LinkedIn-resolve-profile-slug-from-sheet";
import type { CrawlSessionGroup } from "@/types/api";
import { SheetCommentStatus } from "@/components/features/linkedin/dashboard/LinkedIn-SheetCommentStatus";
import { SheetInteractionStatus } from "@/components/features/linkedin/dashboard/LinkedIn-SheetInteractionStatus";
import { buildSheetCommentPatch } from "@/lib/LinkedIn-appComments";
import { buildSheetReactionCell } from "@/components/features/linkedin/dashboard/LinkedIn-post-sheet-engagement";
import {
  pickNum,
  pickPositiveRowNumberFromPost,
  pickStr,
  shortenSessionId,
} from "@/components/features/linkedin/dashboard/LinkedIn-n8n-sheet-helpers";

export interface SessionPostDetailModalProps {
  session: CrawlSessionGroup;
  post: Record<string, unknown>;
  rowNumber: number;
  titleSuffix?: string;
  onClose: () => void;
  dashboardEmail?: string | null;
  linkedinPlaywrightSessionId?: string | null;
  onReactionSucceeded?: (
    rowNum: number,
    patch: Record<string, unknown>,
    postUrlForSync?: string,
  ) => void;
  onRefreshSessions?: () => Promise<void>;
  refreshSessionsBusy?: boolean;
}

function formatDayVi(day: string): string {
  const d = day.trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return day || "—";
  const [y, m, dayNum] = d.split("-");
  return `${dayNum}/${m}/${y}`;
}

export function SessionPostDetailModal({
  session,
  post,
  rowNumber,
  titleSuffix = "",
  onClose,
  dashboardEmail = null,
  linkedinPlaywrightSessionId = null,
  onReactionSucceeded,
  onRefreshSessions,
}: SessionPostDetailModalProps) {
  const { onEngagementSuccess, showEngagementFailure, registerBackgroundSync } =
    useLinkedInEngagementQueue();

  const [syncBusy, setSyncBusy] = useState(false);
  const [syncErr, setSyncErr] = useState<string | null>(null);

  const emailCrawl =
    (session.email_crawl || "").trim() || (dashboardEmail || "").trim();

  const playwrightSessionEmail = useMemo(() => {
    const crawl = emailCrawl.trim();
    if (crawl.includes("@")) return crawl;
    return (dashboardEmail || "").trim() || undefined;
  }, [emailCrawl, dashboardEmail]);

  const engagementPassword = useMemo(() => {
    const creds = readLinkedInCredentials();
    if (!creds?.password) return undefined;
    const credEmail = creds.email.trim().toLowerCase();
    const targets = [
      playwrightSessionEmail?.trim().toLowerCase(),
      emailCrawl.trim().toLowerCase(),
    ].filter((v): v is string => Boolean(v && v.includes("@")));
    if (targets.length === 0) return creds.password;
    if (targets.some((t) => t === credEmail)) return creds.password;
    return undefined;
  }, [emailCrawl, playwrightSessionEmail]);

  const title =
    pickStr(post, ["Nội dung", "content", "title", "Title"]) ||
    `Bài #${rowNumber}${titleSuffix}`;
  const author = pickStr(post, ["Tác giả", "author", "Author"]);
  const content = pickStr(post, ["Nội dung", "content", "text", "body"]);
  const groupName = pickStr(post, ["Tên nhóm", "group_name", "groupName"]);
  const groupUrl = pickStr(post, ["URL_Nhóm", "URL_nhom", "group_url", "groupUrl"]);
  const postUrl = pickStr(post, ["URL_Bài_Viết", "post_url", "postUrl", "url"]);
  const dayRaw = pickStr(post, ["Ngày", "date", "day"]);
  const postedAt = pickStr(post, ["Đăng vào", "posted_at", "created_at"]);
  const likes = pickNum(post, ["Số like", "likes", "like_count"]) || 0;
  const comments = pickNum(post, ["Số comment", "comments", "comment_count"]) || 0;
  const score = pickNum(post, ["Điểm", "score", "Score"]) || 0;
  const canOpenPost = Boolean(postUrl && /^https?:\/\//i.test(postUrl));
  const existingComments = useMemo(() => parseAppCommentsFromPost(post), [post]);

  const runSyncProgress = useCallback(async () => {
    setSyncErr(null);
    if (!canOpenPost) {
      setSyncErr("Chưa có link bài để quét LinkedIn.");
      return;
    }
    if (!emailCrawl) {
      setSyncErr("Thiếu Email_crawl.");
      return;
    }
    const sid = (session.id_session_crawl || "").trim();
    if (!sid) {
      setSyncErr("Thiếu ID_session_crawl.");
      return;
    }

    const pwSession = (linkedinPlaywrightSessionId || "").trim();
    setSyncBusy(true);
    try {
      const profileSlug = await resolveProfileSlugFromSheetForEmail(emailCrawl, {
        post: post as Record<string, unknown>,
        session: session as unknown as Record<string, unknown>,
      });
      const webhookRowNumber = pickPositiveRowNumberFromPost(post) ?? rowNumber;
      const res = await syncPostProgress({
        post_url: postUrl,
        profile_slug: profileSlug,
        Email_crawl: emailCrawl,
        ID_session_crawl: sid,
        row_number: webhookRowNumber,
        sheet_row: post,
        session_id: pwSession || undefined,
        email: playwrightSessionEmail,
        password: engagementPassword,
        auto_login: true,
      });
      if (!res.success) {
        throw new Error(res.message || "Làm mới tiến độ thất bại.");
      }

      const patch: Record<string, unknown> = {};
      if (res.data?.reaction) {
        const cell = buildSheetReactionCell(res.data.reaction as never);
        patch.reaction = cell;
        patch.Reaction = cell;
      } else {
        patch.reaction = "";
        patch.Reaction = "";
      }
      if (res.data?.comments) {
        Object.assign(patch, buildSheetCommentPatch(res.data.comments));
      }

      onReactionSucceeded?.(rowNumber, patch, postUrl);
      onEngagementSuccess("sync");
      await onRefreshSessions?.();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Lỗi không xác định.";
      setSyncErr(message);
      showEngagementFailure("sync", message, post, rowNumber, session);
    } finally {
      setSyncBusy(false);
    }
  }, [
    canOpenPost,
    emailCrawl,
    engagementPassword,
    linkedinPlaywrightSessionId,
    onEngagementSuccess,
    onReactionSucceeded,
    onRefreshSessions,
    playwrightSessionEmail,
    post,
    postUrl,
    rowNumber,
    session,
    showEngagementFailure,
  ]);

  useEffect(() => {
    registerBackgroundSync(null);
    return () => registerBackgroundSync(null);
  }, [registerBackgroundSync]);

  return (
    <Fragment>
      <ModalOverlay onClose={onClose}>
        <div
          className="border-outline-variant bg-surface relative z-10 flex max-h-[min(92vh,800px)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border shadow-2xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="post-detail-title"
        >
          <header className="border-outline-variant shrink-0 border-b px-lg pb-md pt-lg">
            <div className="flex items-start justify-between gap-md">
              <div className="min-w-0 flex-1">
                <span className="bg-primary/10 text-primary inline-flex rounded-full px-sm py-0.5 text-[11px] font-bold uppercase tracking-wide">
                  Chi tiết bài viết
                </span>
                <h3
                  id="post-detail-title"
                  className="text-h3 text-on-surface mt-2 font-semibold leading-snug"
                >
                  {title}
                </h3>
                {author ? (
                  <p className="text-body-sm text-on-surface-variant mt-1">
                    <span className="text-on-surface font-medium">{author}</span>
                    {groupName ? (
                      <>
                        <span className="mx-1">·</span>
                        <span>{groupName}</span>
                      </>
                    ) : null}
                  </p>
                ) : null}
                <div className="mt-3 flex flex-wrap gap-sm">
                  <span className="border-outline-variant bg-surface-container-low inline-flex min-h-[28px] items-center rounded-full border px-md py-1 text-xs font-semibold">
                    <SheetInteractionStatus post={post} variant="chip" />
                  </span>
                  <span className="border-outline-variant bg-surface-container-low inline-flex min-h-[28px] items-center rounded-full border px-md py-1 text-xs font-semibold">
                    <SheetCommentStatus post={post} variant="chip" />
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container shrink-0 rounded-lg p-2 transition-colors"
                aria-label="Đóng"
              >
                <MaterialIcon name="close" className="text-[22px]" />
              </button>
            </div>

            <div className="border-outline-variant bg-surface-container-low/60 mt-md grid grid-cols-2 gap-sm rounded-xl border p-md sm:grid-cols-4">
              <StatPill icon="thumb_up" value={likes} label="thích" />
              <StatPill icon="comment" value={comments} label="bình luận" />
              <StatPill icon="trending_up" value={score} label="điểm" />
              <DateStatCell dayRaw={dayRaw} postedAt={postedAt} />
            </div>

            <div className="mt-md flex flex-wrap gap-sm">
              {groupUrl && /^https?:\/\//i.test(groupUrl) ? (
                <ExternalActionLink href={groupUrl} icon="group">
                  Nhóm LinkedIn
                </ExternalActionLink>
              ) : null}
              {canOpenPost ? (
                <ExternalActionLink href={postUrl} icon="visibility">
                  Xem bài
                </ExternalActionLink>
              ) : null}
              <button
                type="button"
                className="bg-primary text-on-primary hover:bg-primary/90 inline-flex flex-1 items-center justify-center gap-2 rounded-xl px-md py-sm text-sm font-bold disabled:opacity-50 sm:flex-none"
                onClick={() => void runSyncProgress()}
                disabled={syncBusy || !canOpenPost}
              >
                <MaterialIcon
                  name="sync"
                  className={`text-[20px] ${syncBusy ? "animate-spin" : ""}`}
                />
                {syncBusy ? "Đang làm mới…" : "Làm mới tiến độ"}
              </button>
            </div>

            {syncErr ? (
              <p className="text-error mt-3 text-xs font-medium">{syncErr}</p>
            ) : null}
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto px-lg py-md">
            <section className="border-outline-variant/80 bg-surface-container-low/40 rounded-xl border p-md">
              <h4 className="text-label-md text-on-surface-variant mb-2 font-semibold uppercase tracking-wide">
                Nội dung
              </h4>
              {content ? (
                <p className="text-body-md text-on-surface leading-relaxed whitespace-pre-wrap">
                  {content}
                </p>
              ) : (
                <p className="text-body-sm text-on-surface-variant italic">
                  Không có nội dung văn bản trong dữ liệu crawl.
                </p>
              )}
            </section>

            {existingComments.length > 0 ? (
              <section className="border-outline-variant/80 bg-surface-container-low/40 mt-md rounded-xl border p-md">
                <h4 className="text-label-md text-on-surface-variant mb-3 flex items-center gap-2 font-semibold uppercase tracking-wide">
                  <MaterialIcon name="comment" className="text-[16px]" />
                  Bình luận đã ghi nhận ({existingComments.length})
                </h4>
                <ul className="max-h-48 space-y-2 overflow-y-auto">
                  {existingComments.map((c, i) => (
                    <li
                      key={`${appCommentDay(c)}-${i}`}
                      className="border-outline-variant/50 rounded-lg border bg-black/[0.02] px-md py-sm dark:bg-white/[0.03]"
                    >
                      <span className="text-on-surface-variant font-mono text-[10px]">
                        {formatDayVi(appCommentDay(c))}
                      </span>
                      <p className="text-on-surface text-body-sm mt-1 whitespace-pre-wrap">
                        {appCommentContent(c)}
                      </p>
                    </li>
                  ))}
                </ul>
                <p className="text-on-surface-variant mt-3 text-[11px]">
                  Chỉ xem — tương tác trên app đã tắt. Dùng «Làm mới tiến độ» để cập nhật từ LinkedIn.
                </p>
              </section>
            ) : null}

            <p className="text-on-surface-variant mt-lg text-center text-[11px]">
              Phiên{" "}
              <span className="font-mono" title={session.id_session_crawl}>
                {shortenSessionId(session.id_session_crawl)}
              </span>
              {session.email_crawl ? <> · {session.email_crawl}</> : null}
            </p>
          </div>
        </div>
      </ModalOverlay>
    </Fragment>
  );
}

function StatPill({
  icon,
  value,
  label,
}: {
  icon: MaterialSymbolName;
  value: number;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <MaterialIcon name={icon} className="text-primary text-[20px]" />
      <div>
        <p className="text-on-surface text-lg font-bold tabular-nums leading-none">
          {value.toLocaleString("vi-VN")}
        </p>
        <p className="text-on-surface-variant mt-0.5 text-[11px]">{label}</p>
      </div>
    </div>
  );
}

function DateStatCell({
  dayRaw,
  postedAt,
}: {
  dayRaw: string;
  postedAt: string;
}) {
  return (
    <div className="flex flex-col justify-center px-1">
      <span className="text-on-surface-variant text-[10px] font-semibold uppercase">
        Ngày
      </span>
      <span className="text-on-surface text-sm font-semibold tabular-nums">
        {dayRaw ? formatDayVi(dayRaw) : "—"}
      </span>
      {postedAt ? (
        <span className="text-on-surface-variant text-[11px]">Đăng {postedAt}</span>
      ) : null}
    </div>
  );
}

function ExternalActionLink({
  href,
  icon,
  children,
}: {
  href: string;
  icon: MaterialSymbolName;
  children: string;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="border-outline-variant text-primary hover:bg-primary/5 inline-flex items-center gap-1 rounded-xl border px-md py-sm text-xs font-bold uppercase tracking-wide"
    >
      <MaterialIcon name={icon} className="text-[18px]" />
      {children}
      <MaterialIcon name="open_in_new" className="text-[16px]" />
    </a>
  );
}

function ModalOverlay({
  children,
  onClose,
}: {
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center p-md sm:items-center"
      role="presentation"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px]"
        aria-label="Đóng chi tiết bài"
        onClick={onClose}
      />
      {children}
    </div>
  );
}
