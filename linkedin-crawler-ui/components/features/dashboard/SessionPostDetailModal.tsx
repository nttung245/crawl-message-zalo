"use client";

import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { MaterialIcon } from "@/components/ui";
import {
  APP_COMMENT_DAY_KEY,
  appCommentContent,
  appCommentDay,
  buildSheetCommentPatch,
  isoDayLocal,
  parseAppCommentsFromPost,
  type AppCommentEntry,
} from "@/lib/LinkedIn-appComments";
import {
  postLinkedInComment,
  postLinkedInReaction,
} from "@/services/linkedinCrawlerService";
import type { CrawlSessionGroup, PostLinkedInReactionKind } from "@/types/api";
import { useDashboard } from "./dashboard-context";

import {
  REACTION_TOOLBAR_ORDER,
  ReactionToolbarGlyph,
  reactionToolbarLabelVi,
} from "./linkedin-reaction-icons";
import {
  buildSheetReactionCell,
  buildSheetReactionClearPatch,
  ENGAGEMENT_SHEET_FIELD_KEYS,
  parseSheetReaction,
} from "./post-sheet-engagement";
import { SheetCommentStatus } from "./SheetCommentStatus";
import { SheetInteractionStatus } from "./SheetInteractionStatus";
import {
  buildReactionWebhookSheetRow,
  formatCellValue,
  pickNum,
  pickPositiveRowNumberFromPost,
  pickStr,
  shortenSessionId,
  sortedRecordEntries,
} from "./n8n-sheet-helpers";

export interface SessionPostDetailModalProps {
  session: CrawlSessionGroup;
  post: Record<string, unknown>;
  rowNumber: number;
  titleSuffix?: string;
  onClose: () => void;
  /** Email đăng nhập dashboard — fallback resolve session Playwright nếu cần. */
  dashboardEmail?: string | null;
  linkedinPlaywrightSessionId?: string | null;
  /** Sau reaction API thành công — merge ``reaction`` (và có thể mở rộng) vào dòng đang xem + bảng phiên. */
  onReactionSucceeded?: (
    rowNum: number,
    patch: Record<string, unknown>,
    postUrlForSync?: string,
  ) => void;
  /** Sau reaction + webhook thành công — nút OK trong dialog sẽ gọi (làm mới ``get-all-posts``). */
  onRefreshSessions?: () => Promise<void>;
  refreshSessionsBusy?: boolean;
}

function ExternalLink({ href, children }: { href: string; children: string }) {
  const ok = /^https?:\/\//i.test(href);
  if (!ok)
    return (
      <span className="text-on-surface-variant break-all">{children}</span>
    );
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

/** Các key đã hiển thị ở khối marketing — ẩn khỏi danh sách «đầy đủ». */
const KEYS_SHOWN_IN_SUMMARY = new Set([
  "Tên nhóm",
  "group_name",
  "groupName",
  "Nội dung",
  "content",
  "Tác giả",
  "author",
  "Ngày",
  "date",
  "Đăng vào",
  "posted_at",
  "created_at",
  "URL_Nhóm",
  "URL_nhom",
  "group_url",
  "groupUrl",
  "URL_Bài_Viết",
  "post_url",
  "postUrl",
  "Số like",
  "likes",
  "Số comment",
  "comments",
  "Điểm",
  "score",
  "Score",
  "app_comments",
  "linkedin_app_comments",
  "app_comments_json",
  "comments_app",
]);

function formatDayVi(day: string): string {
  const d = day.trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return day || "—";
  const [y, m, dayNum] = d.split("-");
  return `${dayNum}/${m}/${y}`;
}

function buildReactionRollbackPatch(
  source: Record<string, unknown>,
): Record<string, unknown> {
  const reaction = pickStr(source, ["reaction", "Reaction"]);
  return { reaction, Reaction: reaction };
}

export function SessionPostDetailModal({
  session,
  post,
  rowNumber,
  titleSuffix = "",
  onClose,
  dashboardEmail = null,
  linkedinPlaywrightSessionId = null,
  onReactionSucceeded: onReactionSucceededProp,
  onRefreshSessions,
  refreshSessionsBusy = false,
}: SessionPostDetailModalProps) {
  const { updatePostInSessions } = useDashboard();

  const onReactionSucceeded = useCallback(
    (rowNum: number, patch: Record<string, unknown>, postUrlForSync?: string) => {
      onReactionSucceededProp?.(rowNum, patch, postUrlForSync);
      updatePostInSessions?.(
        session.id_session_crawl,
        rowNum,
        patch,
        postUrlForSync,
      );
    },
    [onReactionSucceededProp, updatePostInSessions, session.id_session_crawl],
  );

  const [rxMenuOpen, setRxMenuOpen] = useState(false);
  const [rxBusy, setRxBusy] = useState(false);
  const [rxErr, setRxErr] = useState<string | null>(null);
  const [webhookSuccessKind, setWebhookSuccessKind] = useState<
    null | "reaction" | "comment"
  >(null);
  const [webhookSuccessClosing, setWebhookSuccessClosing] = useState(false);
  const [rxWebhookOkBusy, setRxWebhookOkBusy] = useState(false);
  const [commentComposerOpen, setCommentComposerOpen] = useState(false);
  const [commentDraft, setCommentDraft] = useState("");
  const [cmBusy, setCmBusy] = useState(false);
  const [cmErr, setCmErr] = useState<string | null>(null);
  const [optimisticPatch, setOptimisticPatch] = useState<Record<
    string,
    unknown
  > | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const webhookSuccessCloseTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setOptimisticPatch(null);
  }, [post]);

  const scheduleWebhookSuccessClose = useCallback(() => {
    if (webhookSuccessCloseTimerRef.current !== null) return;
    setWebhookSuccessClosing(true);
    webhookSuccessCloseTimerRef.current = window.setTimeout(() => {
      webhookSuccessCloseTimerRef.current = null;
      setWebhookSuccessKind(null);
      setWebhookSuccessClosing(false);
    }, 180);
  }, []);

  useEffect(() => {
    return () => {
      if (webhookSuccessCloseTimerRef.current !== null) {
        window.clearTimeout(webhookSuccessCloseTimerRef.current);
        webhookSuccessCloseTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (webhookSuccessKind) {
      setWebhookSuccessClosing(false);
    }
  }, [webhookSuccessKind]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (webhookSuccessKind) {
        if (!rxWebhookOkBusy && !refreshSessionsBusy)
          scheduleWebhookSuccessClose();
        return;
      }
      onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    onClose,
    refreshSessionsBusy,
    rxWebhookOkBusy,
    scheduleWebhookSuccessClose,
    webhookSuccessKind,
  ]);

  useEffect(() => {
    if (!rxMenuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setRxMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [rxMenuOpen]);

  const groupName =
    pickStr(post, ["Tên nhóm", "group_name", "groupName"]).trim() ||
    session.group_name?.trim() ||
    "";
  const groupUrl = pickStr(post, [
    "URL_Nhóm",
    "URL_nhom",
    "group_url",
    "groupUrl",
  ]);
  /** Chuỗi cố định cho deps callback — tránh cảnh báo preserve-manual-memoization với object ``post``. */
  const postUrl = useMemo(
    () => pickStr(post, ["URL_Bài_Viết", "post_url", "postUrl"]).trim(),
    [post],
  );
  const author = pickStr(post, ["Tác giả", "author"]);
  const content = pickStr(post, ["Nội dung", "content"]);
  const likes = pickNum(post, ["Số like", "likes"]);
  const comments = pickNum(post, ["Số comment", "comments"]);
  const score = pickNum(post, ["Điểm", "score", "Score"]);
  const dayRaw = pickStr(post, ["Ngày", "date"]).slice(0, 10);
  const postedAt = pickStr(post, ["Đăng vào", "posted_at", "created_at"]);

  const title =
    groupName.length > 0
      ? `Bài ${rowNumber} · ${groupName}`
      : `Bài ${rowNumber}`;
  const canOpenPost = Boolean(postUrl && /^https?:\/\//i.test(postUrl));

  const engagementPost = useMemo(() => {
    if (!optimisticPatch) return post;
    return { ...post, ...optimisticPatch };
  }, [post, optimisticPatch]);

  const { kind: parsedInteractionKind } = parseSheetReaction(engagementPost);

  const extraEntries = sortedRecordEntries(post).filter(
    ([k]) =>
      !KEYS_SHOWN_IN_SUMMARY.has(k) && !ENGAGEMENT_SHEET_FIELD_KEYS.has(k),
  );

  const emailCrawl =
    (session.email_crawl || "").trim() || (dashboardEmail || "").trim();

  const existingComments = useMemo(
    () => parseAppCommentsFromPost(engagementPost),
    [engagementPost],
  );

  const runReaction = useCallback(
    async (kind: PostLinkedInReactionKind) => {
      setRxErr(null);
      if (!canOpenPost) {
        setRxErr("Chưa có link bài để mở LinkedIn.");
        return;
      }
      if (!emailCrawl) {
        setRxErr("Thiếu Email_crawl — không gọi được API reaction.");
        return;
      }
      const sid = (session.id_session_crawl || "").trim();
      if (!sid) {
        setRxErr("Thiếu ID_session_crawl.");
        return;
      }
      const clearingReaction = parsedInteractionKind === kind;

      const patch: Record<string, unknown> = clearingReaction
        ? buildSheetReactionClearPatch()
        : {
            reaction: buildSheetReactionCell(kind),
            Reaction: buildSheetReactionCell(kind),
          };

      setOptimisticPatch(patch);
      onReactionSucceeded?.(rowNumber, patch, postUrl);
      setRxBusy(true);
      setRxMenuOpen(false);

      try {
        const webhookRowNumber =
          pickPositiveRowNumberFromPost(post) ?? rowNumber;
        const res = await postLinkedInReaction({
          post_url: postUrl,
          reaction: kind,
          Email_crawl: emailCrawl,
          ID_session_crawl: sid,
          row_number: webhookRowNumber,
          sheet_row: buildReactionWebhookSheetRow(post, session),
          email: (dashboardEmail || "").trim() || undefined,
          session_id: (linkedinPlaywrightSessionId || "").trim() || undefined,
          post_to_webhook: true,
          clear_reaction: clearingReaction,
        });
        if (!res.success) {
          throw new Error(
            res.message ||
              (clearingReaction
                ? "Gỡ reaction thất bại."
                : "Reaction thất bại."),
          );
        }
        setOptimisticPatch(null);
        if (res.data?.webhook_called) {
          setWebhookSuccessKind("reaction");
        }
      } catch (e) {
        setOptimisticPatch(null);
        onReactionSucceeded?.(
          rowNumber,
          buildReactionRollbackPatch(post),
          postUrl,
        );
        setRxErr(e instanceof Error ? e.message : "Lỗi không xác định.");
      } finally {
        setRxBusy(false);
      }
    },
    [
      canOpenPost,
      dashboardEmail,
      emailCrawl,
      linkedinPlaywrightSessionId,
      onReactionSucceeded,
      post,
      parsedInteractionKind,
      postUrl,
      rowNumber,
      session,
    ],
  );

  const runPostComment = useCallback(async () => {
    setCmErr(null);
    const text = commentDraft.trim();
    if (!text) {
      setCmErr("Nhập nội dung comment.");
      return;
    }
    if (!canOpenPost) {
      setCmErr("Chưa có link bài để mở LinkedIn.");
      return;
    }
    if (!emailCrawl) {
      setCmErr("Thiếu Email_crawl — không gọi được API comment.");
      return;
    }
    const sid = (session.id_session_crawl || "").trim();
    if (!sid) {
      setCmErr("Thiếu ID_session_crawl.");
      return;
    }

    const commentsBeforeSend = parseAppCommentsFromPost(post);
    const optimisticEntry: AppCommentEntry = {
      comment_content: text,
      [APP_COMMENT_DAY_KEY]: isoDayLocal(),
    };
    const optimisticMerged = [...commentsBeforeSend, optimisticEntry];
    const optimisticCommentPatch = buildSheetCommentPatch(optimisticMerged);

    setOptimisticPatch(optimisticCommentPatch);
    onReactionSucceeded?.(rowNumber, optimisticCommentPatch, postUrl);
    setCommentDraft("");
    setCmBusy(true);

    try {
      const webhookRowNumber = pickPositiveRowNumberFromPost(post) ?? rowNumber;
      const res = await postLinkedInComment({
        post_url: postUrl,
        comment_text: text,
        Email_crawl: emailCrawl,
        ID_session_crawl: sid,
        row_number: webhookRowNumber,
        existing_app_comments: commentsBeforeSend,
        sheet_row: buildReactionWebhookSheetRow(post, session),
        email: (dashboardEmail || "").trim() || undefined,
        session_id: (linkedinPlaywrightSessionId || "").trim() || undefined,
        post_to_webhook: true,
      });
      if (!res.success) {
        throw new Error(res.message || "Gửi comment thất bại.");
      }
      const merged: AppCommentEntry[] = (res.data?.app_comments as
        | AppCommentEntry[]
        | undefined) ?? optimisticMerged;
      const patch: Record<string, unknown> = buildSheetCommentPatch(merged);
      setOptimisticPatch(null);
      onReactionSucceeded?.(rowNumber, patch, postUrl);
      if (res.data?.webhook_called) {
        setWebhookSuccessKind("comment");
      }
    } catch (e) {
      setOptimisticPatch(null);
      onReactionSucceeded?.(
        rowNumber,
        buildSheetCommentPatch(commentsBeforeSend),
        postUrl,
      );
      setCommentDraft(text);
      setCmErr(e instanceof Error ? e.message : "Lỗi không xác định.");
    } finally {
      setCmBusy(false);
    }
  }, [
    commentDraft,
    canOpenPost,
    dashboardEmail,
    emailCrawl,
    linkedinPlaywrightSessionId,
    onReactionSucceeded,
    post,
    postUrl,
    rowNumber,
    session,
  ]);

  const handleWebhookOkConfirm = useCallback(async () => {
    setRxWebhookOkBusy(true);
    try {
      await onRefreshSessions?.();
    } finally {
      setRxWebhookOkBusy(false);
      scheduleWebhookSuccessClose();
    }
  }, [onRefreshSessions, scheduleWebhookSuccessClose]);

  const reactionAlreadyMatchesKind = (kind: PostLinkedInReactionKind) =>
    parsedInteractionKind === kind;

  const refreshBusy = refreshSessionsBusy || rxWebhookOkBusy;

  return (
    <Fragment>
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
        <div
          className="border-outline-variant bg-surface relative z-10 flex max-h-[min(92vh,840px)] w-full max-w-3xl flex-col rounded-xl border shadow-2xl"
          role="dialog"
          aria-modal="true"
          aria-labelledby="post-detail-title"
        >
          <div className="border-outline-variant shrink-0 border-b px-lg pb-md pt-lg">
            <div className="flex flex-col gap-md sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-sm">
                  <span className="bg-primary/10 text-primary rounded-full px-sm py-0.5 text-[11px] font-bold uppercase tracking-wide">
                    Chi tiết bài viết
                  </span>
                </div>
                <h3
                  id="post-detail-title"
                  className="text-h3 text-on-surface mt-2 font-semibold leading-snug"
                >
                  {title}
                </h3>
                {author ? (
                  <p className="text-body-sm text-on-surface-variant mt-1">
                    <span className="font-medium text-on-surface">
                      {author}
                    </span>
                    <span className="mx-1">·</span>
                    <span>Tác giả</span>
                  </p>
                ) : null}
                <div className="mt-2 flex flex-wrap items-start gap-sm">
                  <span
                    className="border-outline-variant bg-surface-container-low text-on-surface inline-flex min-h-[28px] items-center gap-2 rounded-full border px-md py-1 text-xs font-semibold"
                    title="Theo cột reaction trên sheet / webhook"
                  >
                    <SheetInteractionStatus post={engagementPost} variant="chip" />
                  </span>
                  <span
                    className="border-outline-variant bg-surface-container-low text-on-surface inline-flex min-h-[28px] items-start rounded-full border px-md py-1 text-xs font-semibold"
                    title="Theo cột comment (automation), không phải số CMT LinkedIn"
                  >
                    <SheetCommentStatus post={engagementPost} variant="chip" />
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-sm sm:justify-end">
                <div className="relative" ref={menuRef}>
                  <button
                    type="button"
                    disabled={rxBusy || cmBusy || !canOpenPost || !emailCrawl}
                    onClick={() => setRxMenuOpen((o) => !o)}
                    className={`border-outline-variant bg-surface-container-low hover:bg-surface-container-high inline-flex items-center gap-1 rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide transition-colors ${
                      canOpenPost && emailCrawl
                        ? "text-primary"
                        : "pointer-events-none opacity-40"
                    }`}
                    title={
                      !emailCrawl
                        ? "Thiếu email phiên crawl"
                        : canOpenPost
                          ? parsedInteractionKind
                            ? "Chọn reaction — bấm lại loại đang chọn để gỡ"
                            : "Chọn reaction — Playwright + webhook sheet"
                          : "Chưa có link bài"
                    }
                  >
                    <ReactionToolbarGlyph
                      kind={parsedInteractionKind ?? "like"}
                      variant="mono"
                      emphasis={Boolean(parsedInteractionKind)}
                      className="shrink-0 text-[20px] leading-none"
                    />
                    {rxBusy ? "Đang đồng bộ…" : "Tương tác"}
                    <MaterialIcon
                      name="chevron_right"
                      className="text-[18px] rotate-90"
                    />
                  </button>
                  {rxMenuOpen ? (
                    <div
                      className="border-outline-variant bg-surface text-primary absolute right-0 z-[70] mt-2 flex max-w-[min(100vw-1.5rem,440px)] flex-nowrap items-center gap-0.5 overflow-x-auto rounded-full border px-2 py-2 shadow-[0_10px_40px_rgb(0_0_0_/_.12)] ring-1 ring-black/[0.04] backdrop-blur-[2px] sm:gap-1 sm:px-3"
                      role="menu"
                    >
                      {REACTION_TOOLBAR_ORDER.map((kind) => {
                        const selected = reactionAlreadyMatchesKind(kind);
                        return (
                          <button
                            key={kind}
                            type="button"
                            role="menuitem"
                            disabled={rxBusy || cmBusy}
                            title={
                              selected
                                ? `${reactionToolbarLabelVi(kind)} — bấm lại để gỡ`
                                : reactionToolbarLabelVi(kind)
                            }
                            aria-label={
                              selected
                                ? `${reactionToolbarLabelVi(kind)}, bấm lại để gỡ reaction`
                                : reactionToolbarLabelVi(kind)
                            }
                            aria-current={selected ? "true" : undefined}
                            className={`outline-none flex min-h-[44px] min-w-[44px] items-center justify-center rounded-full transition-[transform,background-color,box-shadow] duration-200 ease-out hover:scale-[1.08] hover:bg-primary/[0.09] active:scale-[0.96] active:bg-primary/[0.14] disabled:pointer-events-none disabled:opacity-40 focus-visible:ring-primary focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-surface ${
                              selected
                                ? "scale-[1.02] bg-primary/12 ring-1 ring-primary/20"
                                : ""
                            }`}
                            onClick={() => void runReaction(kind)}
                          >
                            <ReactionToolbarGlyph
                              kind={kind}
                              variant="mono"
                              emphasis={selected}
                              className="text-[28px] leading-none sm:text-[30px]"
                            />
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  <button
                    type="button"
                    disabled={rxBusy || cmBusy || !canOpenPost || !emailCrawl}
                    onClick={() => {
                      setCommentComposerOpen((o) => !o);
                      setCmErr(null);
                    }}
                    className={`border-outline-variant bg-surface-container-low hover:bg-surface-container-high inline-flex items-center gap-1 rounded-lg border px-md py-sm text-xs font-bold uppercase tracking-wide transition-colors ${
                      canOpenPost && emailCrawl
                        ? "text-primary"
                        : "pointer-events-none opacity-40"
                    }`}
                    title={
                      !emailCrawl
                        ? "Thiếu email phiên crawl"
                        : canOpenPost
                          ? "Nhập comment — Playwright đăng trên LinkedIn + webhook"
                          : "Chưa có link bài"
                    }
                  >
                    <MaterialIcon name="comment" className="text-[18px]" />
                    {commentComposerOpen ? "Đóng ô comment" : "Bình luận"}
                  </button>
                  {canOpenPost ? (
                    <a
                      href={postUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="border-outline-variant text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface inline-flex items-center gap-0.5 rounded-lg border px-sm py-sm text-[11px] font-bold uppercase tracking-wide"
                      title="Mở bài trên LinkedIn"
                    >
                      <MaterialIcon
                        name="open_in_new"
                        className="text-[14px]"
                      />
                    </a>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded-lg p-2 transition-colors"
                  aria-label="Đóng"
                >
                  <MaterialIcon name="close" className="text-[22px]" />
                </button>
              </div>
            </div>

            {rxErr ? (
              <p className="text-error mt-2 text-xs font-medium">{rxErr}</p>
            ) : null}


            <div className="border-outline-variant bg-surface-container-low/50 mt-md flex flex-wrap gap-x-lg gap-y-sm rounded-lg border px-md py-sm">
              <span className="inline-flex items-center gap-1 text-sm tabular-nums">
                <MaterialIcon
                  name="thumb_up"
                  className="text-on-surface-variant text-[18px]"
                />
                <span className="text-on-surface font-semibold">
                  {likes.toLocaleString("vi-VN")}
                </span>
                <span className="text-on-surface-variant text-xs">thích</span>
              </span>
              <span className="inline-flex items-center gap-1 text-sm tabular-nums">
                <MaterialIcon
                  name="comment"
                  className="text-on-surface-variant text-[18px]"
                />
                <span className="text-on-surface font-semibold">
                  {comments.toLocaleString("vi-VN")}
                </span>
                <span className="text-on-surface-variant text-xs">
                  bình luận
                </span>
              </span>
              <span className="inline-flex items-center gap-1 text-sm tabular-nums">
                <MaterialIcon
                  name="trending_up"
                  className="text-on-surface-variant text-[18px]"
                />
                <span className="text-on-surface font-semibold">
                  {score.toLocaleString("vi-VN")}
                </span>
                <span className="text-on-surface-variant text-xs">điểm</span>
              </span>
              <span className="inline-flex items-center gap-1 text-sm">
                <span className="text-on-surface font-medium">
                  {dayRaw ? formatDayVi(dayRaw) : "—"}
                </span>
                {postedAt ? (
                  <span className="text-on-surface-variant text-xs">
                    · Đăng {postedAt}
                  </span>
                ) : null}
              </span>
            </div>

            <div className="mt-md flex flex-wrap gap-sm">
              {groupUrl && /^https?:\/\//i.test(groupUrl) ? (
                <a
                  href={groupUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="border-primary text-primary hover:bg-primary/5 inline-flex items-center gap-1 rounded-lg border bg-transparent px-md py-sm text-xs font-bold uppercase tracking-wide"
                >
                  <MaterialIcon name="group" className="text-[18px]" />
                  Nhóm LinkedIn
                  <MaterialIcon name="open_in_new" className="text-[16px]" />
                </a>
              ) : null}
              {canOpenPost ? (
                <a
                  href={postUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="border-primary text-primary hover:bg-primary/5 inline-flex items-center gap-1 rounded-lg border bg-transparent px-md py-sm text-xs font-bold uppercase tracking-wide"
                >
                  <MaterialIcon name="visibility" className="text-[18px]" />
                  Xem bài trên LinkedIn
                  <MaterialIcon name="open_in_new" className="text-[16px]" />
                </a>
              ) : null}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-lg py-md flex flex-col gap-md">
            {commentComposerOpen ? (
              <div className="border-outline-variant bg-surface-container-low/40 rounded-xl border p-md shadow-sm">
                <p className="text-label-md text-on-surface-variant mb-2 font-semibold uppercase tracking-wide">
                  Comment tại đây
                </p>
                <textarea
                  value={commentDraft}
                  onChange={(e) => setCommentDraft(e.target.value)}
                  rows={4}
                  disabled={cmBusy}
                  placeholder="Nhập nội dung bình luận…"
                  className="border-outline-variant bg-surface text-body-sm text-on-surface focus:ring-primary min-h-[96px] w-full resize-y rounded-lg border px-md py-sm outline-none focus:ring-2 disabled:opacity-50"
                />
                {cmErr ? (
                  <p className="text-error mt-2 text-xs font-medium">{cmErr}</p>
                ) : null}
                <div className="mt-md flex justify-end gap-sm">
                  <button
                    type="button"
                    disabled={cmBusy}
                    className="border-outline-variant text-on-surface hover:bg-surface-container-high rounded-lg border px-md py-sm text-xs font-bold uppercase transition-colors"
                    onClick={() => {
                      setCommentComposerOpen(false);
                      setCmErr(null);
                    }}
                  >
                    Đóng
                  </button>
                  <button
                    type="button"
                    disabled={
                      cmBusy ||
                      !canOpenPost ||
                      !emailCrawl ||
                      !commentDraft.trim()
                    }
                    className="bg-primary text-on-primary hover:bg-primary-container rounded-lg px-md py-sm text-xs font-bold uppercase disabled:opacity-45 transition-colors shadow-sm"
                    onClick={() => void runPostComment()}
                  >
                    {cmBusy ? "Đang gửi…" : "Gửi comment"}
                  </button>
                </div>
              </div>
            ) : null}
            <section className="border-outline-variant bg-surface-container-low/30 rounded-xl border p-md">
              <h4 className="text-label-md text-on-surface-variant mb-2 font-semibold uppercase tracking-wide">
                Nội dung bài viết
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
              <section className="border-outline-variant bg-surface-container-low/30 rounded-xl border p-md">
                <h4 className="text-label-md text-on-surface-variant mb-3 font-semibold uppercase tracking-wide flex items-center gap-2">
                  <MaterialIcon name="comment" className="text-[16px]" />
                  Comments đã gửi ({existingComments.length})
                </h4>
                <ul className="space-y-2">
                  {existingComments.map((c, i) => (
                    <li
                      key={`${appCommentDay(c)}-${i}-${appCommentContent(c).slice(0, 24)}`}
                      className="border-outline-variant/60 rounded-lg border bg-black/[0.02] px-md py-sm dark:bg-white/[0.03]"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-on-surface-variant font-mono text-xs">
                          {formatDayVi(appCommentDay(c))}
                        </span>
                      </div>
                      <p className="text-on-surface text-body-sm mt-1 whitespace-pre-wrap">
                        {appCommentContent(c)}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <details className="group border-outline-variant bg-surface-container-low/20 rounded-xl border">
              <summary className="text-body-sm text-on-surface cursor-pointer list-none px-md py-md font-semibold [&::-webkit-details-marker]:hidden">
                <span className="inline-flex items-center gap-2">
                  <MaterialIcon name="table_view" className="text-[20px]" />
                  Trường dữ liệu đầy đủ (API / sheet)
                  <MaterialIcon
                    name="chevron_right"
                    className="text-[20px] transition-transform group-open:rotate-90"
                  />
                </span>
              </summary>
              <div className="border-outline-variant border-t px-md py-sm pb-md">
                <p className="text-body-sm text-on-surface-variant mb-3">
                  Dành cho kiểm tra hoặc xuất báo cáo — các thông tin chính đã
                  hiển thị phía trên.
                </p>
                <dl className="space-y-0 text-sm">
                  {extraEntries.length === 0 ? (
                    <p className="text-on-surface-variant text-xs italic">
                      Không còn trường bổ sung.
                    </p>
                  ) : (
                    extraEntries.map(([k, v]) => (
                      <div
                        key={k}
                        className="border-outline-variant/70 grid grid-cols-1 gap-1 border-b py-2 last:border-0 sm:grid-cols-[minmax(0,200px)_1fr]"
                      >
                        <dt className="text-on-surface-variant font-medium">
                          {k}
                        </dt>
                        <dd className="text-on-surface min-w-0 break-words">
                          {typeof v === "string" && /^https?:\/\//i.test(v) ? (
                            <ExternalLink href={v}>{v}</ExternalLink>
                          ) : (
                            formatCellValue(v)
                          )}
                        </dd>
                      </div>
                    ))
                  )}
                </dl>
              </div>
            </details>

            <p className="text-on-surface-variant text-center text-[11px]">
              Phiên:{" "}
              <span className="font-mono" title={session.id_session_crawl}>
                {shortenSessionId(session.id_session_crawl)}
              </span>
              {session.email_crawl ? (
                <>
                  {" "}
                  · Email crawl:{" "}
                  <span className="break-all">{session.email_crawl}</span>
                </>
              ) : null}
            </p>
          </div>
        </div>
      </div>

      {webhookSuccessKind ? (
        <div
          className="fixed inset-0 z-[75] flex items-end justify-center p-md sm:items-center"
          role="presentation"
        >
          <button
            type="button"
            className={`absolute inset-0 bg-black/55 backdrop-blur-md ${
              webhookSuccessClosing
                ? "rx-webhook-overlay--out"
                : "rx-webhook-overlay--in"
            }`}
            aria-label="Đóng thông báo"
            onClick={() => !refreshBusy && scheduleWebhookSuccessClose()}
          />
          <div
            className={`border-outline-variant/70 bg-surface-container-lowest relative z-10 w-[min(92vw,500px)] overflow-hidden rounded-2xl border shadow-[0_24px_60px_rgb(0_0_0_/_.18)] ring-1 ring-primary/10 ${
              webhookSuccessClosing
                ? "rx-webhook-dialog--out"
                : "rx-webhook-dialog--in"
            }`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="rx-webhook-ok-title"
          >
            <div className="from-primary/20 via-primary/5 h-1 bg-gradient-to-r to-transparent" />
            <div className="p-lg sm:p-xl">
              <div className="flex items-start gap-md">
                <span className="bg-primary/10 text-primary inline-flex size-11 shrink-0 items-center justify-center rounded-full">
                  <MaterialIcon
                    name={
                      webhookSuccessKind === "reaction" ? "favorite" : "comment"
                    }
                    className="text-[24px]"
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <span className="bg-primary/10 text-primary inline-flex rounded-full px-sm py-0.5 text-[10px] font-bold tracking-[0.12em] uppercase">
                    Thành công
                  </span>
                  <h3
                    id="rx-webhook-ok-title"
                    className="text-h2 text-on-surface mt-2 font-semibold tracking-tight"
                  >
                    {webhookSuccessKind === "reaction"
                      ? "Tương tác thành công"
                      : "Bình luận thành công"}
                  </h3>
                  <p className="text-body-md text-on-surface-variant mt-sm leading-relaxed whitespace-pre-line">
                    {webhookSuccessKind === "reaction"
                      ? "Bạn đã tương tác với bài viết thành công trên Makee, sẽ cập nhật tiến độ thật trong vòng 30s"
                      : "Bạn đã bình luận trên bài viết thành công trên Makee, sẽ cập nhật tiến độ thật trong vòng 30s"}
                  </p>
                </div>
              </div>
              <div className="mt-lg flex flex-col-reverse gap-sm sm:flex-row sm:justify-end">
                <button
                  type="button"
                  className="border-outline-variant text-on-surface hover:bg-surface-container-high rounded-xl border px-lg py-sm text-sm font-bold uppercase transition-colors disabled:opacity-50"
                  onClick={() => !refreshBusy && scheduleWebhookSuccessClose()}
                  disabled={refreshBusy}
                >
                  Đóng
                </button>
                <button
                  type="button"
                  className="bg-primary text-on-primary hover:bg-primary-container min-w-28 rounded-xl px-lg py-sm text-sm font-bold uppercase shadow-[0_10px_24px_rgb(0_93_143_/_.22)] transition-[transform,background-color,box-shadow] duration-200 ease-out hover:shadow-[0_12px_28px_rgb(0_93_143_/_.28)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => void handleWebhookOkConfirm()}
                  disabled={refreshBusy}
                >
                  {refreshBusy ? "Đang làm mới…" : "OK"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </Fragment>
  );
}
