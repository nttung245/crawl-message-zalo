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
import { useLinkedInEngagementQueue } from "@/components/features/linkedin/dashboard/linkedin-engagement-queue-context";
import type { EngagementFeedbackKind } from "@/lib/linkedin-engagement-feedback";
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
  deleteLinkedInComment,
  editLinkedInComment,
  getMyProfileSlug,
  syncPostProgress,
} from "@/services/linkedinCrawlerService";
import { resolveProfileSlugFromSheetForEmail } from "@/lib/LinkedIn-resolve-profile-slug-from-sheet";
import { useDashboard } from "@/components/features/dashboard/dashboard-context";
import type { CrawlSessionGroup, PostLinkedInReactionKind } from "@/types/api";

import {
  REACTION_TOOLBAR_ORDER,
  ReactionToolbarGlyph,
  reactionToolbarLabelVi,
} from "@/components/features/linkedin/dashboard/LinkedIn-reaction-icons";
import {
  buildSheetReactionCell,
  buildSheetReactionClearPatch,
  ENGAGEMENT_SHEET_FIELD_KEYS,
  parseSheetReaction,
} from "@/components/features/linkedin/dashboard/LinkedIn-post-sheet-engagement";
import { SheetCommentStatus } from "@/components/features/linkedin/dashboard/LinkedIn-SheetCommentStatus";
import { SheetInteractionStatus } from "@/components/features/linkedin/dashboard/LinkedIn-SheetInteractionStatus";
import {
  buildReactionWebhookSheetRow,
  formatCellValue,
  pickNum,
  pickPositiveRowNumberFromPost,
  pickStr,
  shortenSessionId,
  sortedRecordEntries,
} from "@/components/features/linkedin/dashboard/LinkedIn-n8n-sheet-helpers";

/** Gọi API Playwright ngay khi user bấm — không xếp hàng sau sync/refresh (tránh VM chậm không thấy log API). */
function runLinkedInEngagementApi<T>(options: {
  run: () => Promise<T>;
  onSuccess?: (result: T) => void;
  onFailure?: (error: Error) => void;
}): void {
  void (async () => {
    try {
      const result = await options.run();
      options.onSuccess?.(result);
    } catch (error) {
      options.onFailure?.(
        error instanceof Error ? error : new Error(String(error)),
      );
    }
  })();
}

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

  const {
    onEngagementSuccess,
    enqueuePostEngagementSync,
    showEngagementFailure,
    registerBackgroundSync,
  } = useLinkedInEngagementQueue();

  const [rxMenuOpen, setRxMenuOpen] = useState(false);
  const [rxErr, setRxErr] = useState<string | null>(null);
  const [optimisticPatch, setOptimisticPatch] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [commentComposerOpen, setCommentComposerOpen] = useState(false);
  const [commentDraft, setCommentDraft] = useState("");
  const [cmErr, setCmErr] = useState<string | null>(null);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncErr, setSyncErr] = useState<string | null>(null);

  const [deleteCommentErr, setDeleteCommentErr] = useState<string | null>(null);
  const [editingCommentIndex, setEditingCommentIndex] = useState<number | null>(
    null,
  );
  const [editCommentErr, setEditCommentErr] = useState<string | null>(null);
  const [editCommentNewText, setEditCommentNewText] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setOptimisticPatch(null);
  }, [post]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

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
    (kind: PostLinkedInReactionKind) => {
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
      const rollbackPatch = buildReactionRollbackPatch(post);
      const patch: Record<string, unknown> = clearingReaction
        ? buildSheetReactionClearPatch()
        : {
            reaction: buildSheetReactionCell(kind),
            Reaction: buildSheetReactionCell(kind),
          };
      const feedbackKind: EngagementFeedbackKind = clearingReaction
        ? "clear_reaction"
        : "reaction";

      setOptimisticPatch(patch);
      onReactionSucceeded?.(rowNumber, patch, postUrl);
      onEngagementSuccess(feedbackKind);
      setRxMenuOpen(false);

      const webhookRowNumber =
        pickPositiveRowNumberFromPost(post) ?? rowNumber;

      runLinkedInEngagementApi({
        run: async () => {
          const res = await postLinkedInReaction({
            post_url: postUrl,
            reaction: kind,
            Email_crawl: emailCrawl,
            ID_session_crawl: sid,
            row_number: webhookRowNumber,
            sheet_row: buildReactionWebhookSheetRow(post, session),
            email: (dashboardEmail || "").trim() || undefined,
            session_id:
              (linkedinPlaywrightSessionId || "").trim() || undefined,
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
        },
        onSuccess: () => {
          enqueuePostEngagementSync();
        },
        onFailure: (error) => {
          setOptimisticPatch(null);
          onReactionSucceeded?.(rowNumber, rollbackPatch, postUrl);
          showEngagementFailure(feedbackKind, error.message, post, rowNumber, session);
        },
      });
    },
    [
      canOpenPost,
      dashboardEmail,
      emailCrawl,
      enqueuePostEngagementSync,
      linkedinPlaywrightSessionId,
      onEngagementSuccess,
      onReactionSucceeded,
      post,
      parsedInteractionKind,
      postUrl,
      rowNumber,
      session,
      showEngagementFailure,
    ],
  );

  const runPostComment = useCallback(() => {
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
    const rollbackPatch = buildSheetCommentPatch(commentsBeforeSend);

    setOptimisticPatch(optimisticCommentPatch);
    onReactionSucceeded?.(rowNumber, optimisticCommentPatch, postUrl);
    onEngagementSuccess("comment");
    setCommentDraft("");

    const webhookRowNumber = pickPositiveRowNumberFromPost(post) ?? rowNumber;

    runLinkedInEngagementApi({
      run: async () => {
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
          timeout_ms: 120000,
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
      },
      onSuccess: () => {
        enqueuePostEngagementSync();
      },
      onFailure: (error) => {
        setOptimisticPatch(null);
        onReactionSucceeded?.(rowNumber, rollbackPatch, postUrl);
        setCommentDraft(text);
        showEngagementFailure("comment", error.message, post, rowNumber, session);
      },
    });
  }, [
    commentDraft,
    canOpenPost,
    dashboardEmail,
    emailCrawl,
    enqueuePostEngagementSync,
    linkedinPlaywrightSessionId,
    onEngagementSuccess,
    onReactionSucceeded,
    post,
    postUrl,
    rowNumber,
    session,
    showEngagementFailure,
  ]);

  const runDeleteComment = useCallback(
    (commentIndex: number) => {
      setDeleteCommentErr(null);
      const commentsBeforeDelete = parseAppCommentsFromPost(post);
      if (commentIndex < 0 || commentIndex >= commentsBeforeDelete.length) {
        setDeleteCommentErr("Comment không hợp lệ.");
        return;
      }
      if (!canOpenPost) {
        setDeleteCommentErr("Chưa có link bài để mở LinkedIn.");
        return;
      }
      if (!emailCrawl) {
        setDeleteCommentErr("Thiếu Email_crawl — không gọi được API delete.");
        return;
      }
      const sid = (session.id_session_crawl || "").trim();
      if (!sid) {
        setDeleteCommentErr("Thiếu ID_session_crawl.");
        return;
      }

      const commentToDelete = commentsBeforeDelete[commentIndex];
      if (!commentToDelete) {
        setDeleteCommentErr("Comment không tìm thấy.");
        return;
      }

      const commentText = appCommentContent(commentToDelete).trim();
      if (!commentText) {
        setDeleteCommentErr("Nội dung comment rỗng.");
        return;
      }

      const pwSession = (linkedinPlaywrightSessionId || "").trim();
      const pwEmail =
        (dashboardEmail || "").trim() ||
        (emailCrawl.includes("@") ? emailCrawl.trim() : "");
      if (!pwSession && !pwEmail) {
        setDeleteCommentErr(
          "Thiếu session Playwright hoặc email — không gọi được API lấy profile slug (cần giống khi reaction/comment).",
        );
        return;
      }

      const rollbackPatch = buildSheetCommentPatch(commentsBeforeDelete);
      const optimisticPatchDelete = buildSheetCommentPatch([]);
      setOptimisticPatch(optimisticPatchDelete);
      onReactionSucceeded?.(rowNumber, optimisticPatchDelete, postUrl);
      onEngagementSuccess("delete_comment");

      runLinkedInEngagementApi({
        run: async () => {
          const slugRes = await getMyProfileSlug({
            sessionId: pwSession || null,
            email: pwEmail || null,
          });
          if (!slugRes.success || !slugRes.data?.profile_slug?.trim()) {
            throw new Error(
              slugRes.message ||
                "Không lấy được profile slug từ LinkedIn. Kiểm tra session đăng nhập.",
            );
          }
          const profileSlug = slugRes.data.profile_slug.trim();
          const webhookRowNumber =
            pickPositiveRowNumberFromPost(post) ?? rowNumber;
          const res = await deleteLinkedInComment({
            profile_slug: profileSlug,
            post_url: postUrl,
            comment_text: commentText,
            Email_crawl: emailCrawl,
            ID_session_crawl: sid,
            row_number: webhookRowNumber,
            sheet_row: buildReactionWebhookSheetRow(post, session),
            email: (dashboardEmail || "").trim() || undefined,
            session_id:
              (linkedinPlaywrightSessionId || "").trim() || undefined,
            post_to_webhook: true,
            max_scroll: 8,
            timeout_ms: 120000,
          });

          if (!res.success) {
            throw new Error(res.message || "Xóa comment thất bại.");
          }

          setOptimisticPatch(null);
        },
        onSuccess: () => {
          enqueuePostEngagementSync();
        },
        onFailure: (error) => {
          setOptimisticPatch(null);
          onReactionSucceeded?.(rowNumber, rollbackPatch, postUrl);
          showEngagementFailure("delete_comment", error.message, post, rowNumber, session);
        },
      });
    },
    [
      canOpenPost,
      dashboardEmail,
      emailCrawl,
      enqueuePostEngagementSync,
      linkedinPlaywrightSessionId,
      onEngagementSuccess,
      onReactionSucceeded,
      post,
      postUrl,
      rowNumber,
      session,
      showEngagementFailure,
    ],
  );

const runSyncProgress = useCallback(
  async (options?: { silent?: boolean; throwOnError?: boolean }) => {
    setSyncErr(null);

    if (!canOpenPost) {
      const message = "Chưa có link bài để mở LinkedIn.";
      setSyncErr(message);
      if (options?.throwOnError) throw new Error(message);
      return;
    }

    if (!emailCrawl) {
      const message = "Thiếu Email_crawl.";
      setSyncErr(message);
      if (options?.throwOnError) throw new Error(message);
      return;
    }

    const sid = (session.id_session_crawl || "").trim();

    if (!sid) {
      const message = "Thiếu ID_session_crawl.";
      setSyncErr(message);
      if (options?.throwOnError) throw new Error(message);
      return;
    }

    const pwSession = (linkedinPlaywrightSessionId || "").trim();
    const pwEmail =
      (dashboardEmail || "").trim() ||
      (emailCrawl.includes("@") ? emailCrawl.trim() : "");

    setSyncBusy(true);

    try {
      const profileSlug = await resolveProfileSlugFromSheetForEmail(emailCrawl, {
        post: post as Record<string, unknown>,
        session: session as unknown as Record<string, unknown>,
      });
      const webhookRowNumber =
        pickPositiveRowNumberFromPost(post) ?? rowNumber;

      const res = await syncPostProgress({
        post_url: postUrl,
        profile_slug: profileSlug,
        Email_crawl: emailCrawl,
        ID_session_crawl: sid,
        row_number: webhookRowNumber,
        sheet_row: post,
        session_id: pwSession || undefined,
        email: pwEmail || undefined,
      });

      if (!res.success) {
        throw new Error(res.message || "Làm mới tiến độ thất bại.");
      }

      const patch: Record<string, unknown> = {};

      if (res.data?.reaction) {
        patch.reaction = buildSheetReactionCell(res.data.reaction as any);
        patch.Reaction = buildSheetReactionCell(res.data.reaction as any);
      } else {
        patch.reaction = "";
        patch.Reaction = "";
      }

      if (res.data?.comments) {
        patch.app_comments = res.data.comments;
      }

      if (res.data?.total_reactions !== undefined) {
        patch["Số like"] = res.data.total_reactions;
        patch.likes = res.data.total_reactions;
      }

      if (res.data?.total_comments !== undefined) {
        patch["Số comment"] = res.data.total_comments;
        patch.comments = res.data.total_comments;
      }

      onReactionSucceeded?.(rowNumber, patch, postUrl);

      if (!options?.silent) {
        onEngagementSuccess("sync");
      }
    } catch (e) {
      setSyncErr(e instanceof Error ? e.message : "Lỗi không xác định.");

      if (options?.throwOnError) {
        throw e;
      }
    } finally {
      setSyncBusy(false);
    }
  },
  [
    canOpenPost,
    dashboardEmail,
    emailCrawl,
    linkedinPlaywrightSessionId,
    onEngagementSuccess,
    onReactionSucceeded,
    post,
    postUrl,
    rowNumber,
    session,
  ],
);

  useEffect(() => {
    registerBackgroundSync(() =>
      runSyncProgress({ silent: true, throwOnError: true }),
    );
    return () => registerBackgroundSync(null);
  }, [registerBackgroundSync, runSyncProgress]);

  const runEditComment = useCallback(
    (commentIndex: number) => {
      setEditCommentErr(null);
      const commentsBeforeEdit = parseAppCommentsFromPost(post);
      if (commentIndex < 0 || commentIndex >= commentsBeforeEdit.length) {
        setEditCommentErr("Comment không hợp lệ.");
        return;
      }
      if (!canOpenPost) {
        setEditCommentErr("Chưa có link bài để mở LinkedIn.");
        return;
      }
      if (!emailCrawl) {
        setEditCommentErr("Thiếu Email_crawl — không gọi được API edit.");
        return;
      }
      const sid = (session.id_session_crawl || "").trim();
      if (!sid) {
        setEditCommentErr("Thiếu ID_session_crawl.");
        return;
      }

      const commentToEdit = commentsBeforeEdit[commentIndex];
      if (!commentToEdit) {
        setEditCommentErr("Comment không tìm thấy.");
        return;
      }

      const oldCommentText = appCommentContent(commentToEdit).trim();
      if (!oldCommentText) {
        setEditCommentErr("Nội dung comment cũ rỗng.");
        return;
      }

      const newCommentText = editCommentNewText.trim();
      if (!newCommentText) {
        setEditCommentErr("Nội dung comment mới rỗng.");
        return;
      }

      if (oldCommentText === newCommentText) {
        setEditCommentErr("Comment mới giống comment cũ.");
        return;
      }

      const pwSession = (linkedinPlaywrightSessionId || "").trim();
      const pwEmail =
        (dashboardEmail || "").trim() ||
        (emailCrawl.includes("@") ? emailCrawl.trim() : "");
      if (!pwSession && !pwEmail) {
        setEditCommentErr(
          "Thiếu session Playwright hoặc email — không gọi được API lấy profile slug.",
        );
        return;
      }

      const rollbackPatch = buildSheetCommentPatch(commentsBeforeEdit);
      const editedComments = commentsBeforeEdit.map((entry, idx) =>
        idx === commentIndex
          ? { ...entry, comment_content: newCommentText }
          : entry,
      );
      const optimisticEditPatch = buildSheetCommentPatch(editedComments);

      setOptimisticPatch(optimisticEditPatch);
      onReactionSucceeded?.(rowNumber, optimisticEditPatch, postUrl);
      onEngagementSuccess("edit_comment");
      setEditingCommentIndex(null);
      setEditCommentNewText("");

      runLinkedInEngagementApi({
        run: async () => {
          const slugRes = await getMyProfileSlug({
            sessionId: pwSession || null,
            email: pwEmail || null,
          });
          if (!slugRes.success || !slugRes.data?.profile_slug?.trim()) {
            throw new Error(
              slugRes.message ||
                "Không lấy được profile slug từ LinkedIn. Kiểm tra session đăng nhập.",
            );
          }
          const profileSlug = slugRes.data.profile_slug.trim();
          const webhookRowNumber =
            pickPositiveRowNumberFromPost(post) ?? rowNumber;
          const res = await editLinkedInComment({
            profile_slug: profileSlug,
            post_url: postUrl,
            comment_text: oldCommentText,
            new_comment_text: newCommentText,
            Email_crawl: emailCrawl,
            ID_session_crawl: sid,
            row_number: webhookRowNumber,
            sheet_row: buildReactionWebhookSheetRow(post, session),
            email: (dashboardEmail || "").trim() || undefined,
            session_id:
              (linkedinPlaywrightSessionId || "").trim() || undefined,
            post_to_webhook: true,
            timeout_ms: 120000,
          });

          if (!res.success) {
            throw new Error(res.message || "Chỉnh sửa comment thất bại.");
          }

          setOptimisticPatch(null);
        },
        onSuccess: () => {
          enqueuePostEngagementSync();
        },
        onFailure: (error) => {
          setOptimisticPatch(null);
          onReactionSucceeded?.(rowNumber, rollbackPatch, postUrl);
          setEditingCommentIndex(commentIndex);
          setEditCommentNewText(newCommentText);
          showEngagementFailure("edit_comment", error.message, post, rowNumber, session);
        },
      });
    },
    [
      editCommentNewText,
      canOpenPost,
      dashboardEmail,
      emailCrawl,
      enqueuePostEngagementSync,
      linkedinPlaywrightSessionId,
      onEngagementSuccess,
      onReactionSucceeded,
      post,
      postUrl,
      rowNumber,
      session,
      showEngagementFailure,
    ],
  );

  const reactionAlreadyMatchesKind = (kind: PostLinkedInReactionKind) =>
    parsedInteractionKind === kind;

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
                    disabled={!canOpenPost || !emailCrawl}
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
                    Tương tác
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
                            disabled={!canOpenPost || !emailCrawl}
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
                    disabled={!canOpenPost || !emailCrawl}
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

            {commentComposerOpen ? (
              <div className="border-outline-variant bg-surface-container-low/40 mt-md rounded-xl border p-md">
                <p className="text-label-md text-on-surface-variant mb-2 font-semibold uppercase tracking-wide">
                  Comment tại đây
                </p>
                <textarea
                  value={commentDraft}
                  onChange={(e) => setCommentDraft(e.target.value)}
                  rows={4}
                  placeholder="Nhập nội dung bình luận…"
                  className="border-outline-variant bg-surface text-body-sm text-on-surface focus:ring-primary min-h-[96px] w-full resize-y rounded-lg border px-md py-sm outline-none focus:ring-2 disabled:opacity-50"
                />
                {existingComments.length > 0 ? (
                  <div className="mt-md">
                    <p className="text-body-xs text-on-surface-variant mb-1 font-semibold uppercase">
                      Đã gửi ({existingComments.length})
                    </p>
                    <ul className="max-h-36 space-y-2 overflow-y-auto text-xs">
                      {existingComments.map((c, i) => (
                        <li
                          key={`${appCommentDay(c)}-${i}-${appCommentContent(c).slice(0, 24)}`}
                          className="border-outline-variant/60 rounded-md border bg-black/[0.02] px-sm py-1.5 dark:bg-white/[0.03]"
                        >
                          <span className="text-on-surface-variant font-mono text-[10px]">
                            {formatDayVi(appCommentDay(c))}
                          </span>
                          <p className="text-on-surface mt-0.5 whitespace-pre-wrap">
                            {appCommentContent(c)}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {cmErr ? (
                  <p className="text-error mt-2 text-xs font-medium">{cmErr}</p>
                ) : null}
                <div className="mt-md flex justify-end gap-sm">
                  <button
                    type="button"
                    className="border-outline-variant text-on-surface hover:bg-surface-container-high rounded-lg border px-md py-sm text-xs font-bold uppercase"
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
                      !canOpenPost ||
                      !emailCrawl ||
                      !commentDraft.trim()
                    }
                    className="bg-primary text-on-primary hover:bg-primary-container rounded-lg px-md py-sm text-xs font-bold uppercase disabled:opacity-45"
                    onClick={() => runPostComment()}
                  >
                    Gửi comment
                  </button>
                </div>
              </div>
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
              <button
                type="button"
                className="border-primary text-primary hover:bg-primary/5 inline-flex items-center gap-1 rounded-lg border bg-transparent px-md py-sm text-xs font-bold uppercase tracking-wide disabled:opacity-50"
                onClick={() => void runSyncProgress()}
                disabled={syncBusy}
                title="Quét lại bài viết này trên LinkedIn để cập nhật reaction và comments thực tế"
              >
                <MaterialIcon
                  name="sync"
                  className={`text-[18px] ${syncBusy ? "animate-spin" : ""}`}
                />
                {syncBusy ? "Đang quét…" : "Làm mới tiến độ"}
              </button>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-lg py-md">
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
              <section className="border-outline-variant bg-surface-container-low/30 mt-md rounded-xl border p-md">
                <h4 className="text-label-md text-on-surface-variant mb-3 font-semibold uppercase tracking-wide flex items-center gap-2">
                  <MaterialIcon name="comment" className="text-[16px]" />
                  Bình luận của bạn trên LinkedIn ({existingComments.length})
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
                        <div className="flex gap-1">
                          <button
                            type="button"
                            className="text-on-surface-variant hover:text-primary disabled:opacity-30 rounded px-1 py-0.5 text-xs transition-colors"
                            onClick={() => {
                              setEditingCommentIndex(i);
                              setEditCommentNewText(appCommentContent(c));
                              setEditCommentErr(null);
                            }}
                            disabled={editingCommentIndex === i}
                            title="Chỉnh sửa comment này trên LinkedIn"
                          >
                            <MaterialIcon
                              name="edit"
                              className="inline text-[14px]"
                            />
                          </button>
                          <button
                            type="button"
                            className="text-on-surface-variant hover:text-error disabled:opacity-30 rounded px-1 py-0.5 text-xs transition-colors"
                            onClick={() => runDeleteComment(i)}
                            title="Xóa comment này từ LinkedIn"
                          >
                            <MaterialIcon
                              name="delete"
                              className="inline text-[14px]"
                            />
                          </button>
                        </div>
                      </div>
                      <p className="text-on-surface text-body-sm mt-1 whitespace-pre-wrap">
                        {appCommentContent(c)}
                      </p>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            {deleteCommentErr ? (
              <div className="border-error-container bg-error/10 mt-md rounded-lg border px-md py-sm">
                <p className="text-error text-xs font-medium">
                  {deleteCommentErr}
                </p>
              </div>
            ) : null}
            {editCommentErr ? (
              <div className="border-error-container bg-error/10 mt-md rounded-lg border px-md py-sm">
                <p className="text-error text-xs font-medium">
                  {editCommentErr}
                </p>
              </div>
            ) : null}
            {syncErr ? (
              <div className="border-error-container bg-error/10 mt-md rounded-lg border px-md py-sm">
                <p className="text-error text-xs font-medium">{syncErr}</p>
              </div>
            ) : null}
            {editingCommentIndex !== null &&
            editingCommentIndex >= 0 &&
            editingCommentIndex < existingComments.length ? (
              <div
                className="fixed inset-0 z-50 flex items-end justify-center p-md sm:items-center"
                role="presentation"
              >
                <button
                  type="button"
                  className="absolute inset-0 bg-black/55 backdrop-blur-md"
                  onClick={() => {
                    setEditingCommentIndex(null);
                    setEditCommentNewText("");
                    setEditCommentErr(null);
                  }}
                />
                <div className="bg-surface border-outline-variant relative z-10 w-full min-w-[320px] sm:min-w-[420px] max-w-md max-h-[80vh] rounded-2xl border shadow-lg flex flex-col overflow-hidden">
                  <div className="px-6 py-4 flex-shrink-0">
                    <h2 className="text-on-surface text-title-md font-semibold">
                      Chỉnh sửa comment
                    </h2>
                  </div>
                  <div className="flex-1 overflow-y-auto px-6 pb-4">
                    <textarea
                      value={editCommentNewText}
                      onChange={(e) =>
                        setEditCommentNewText(e.currentTarget.value)
                      }
                      className="text-on-surface bg-surface-container-high border-outline-variant w-full rounded-lg border px-3 py-2 text-sm outline-none focus:border-primary focus:border-2 resize-none"
                      rows={6}
                      placeholder="Nhập comment mới..."
                      autoFocus
                    />
                  </div>
                  <div className="flex-shrink-0 flex gap-2 justify-end px-6 py-4 border-outline-variant border-t">
                    <button
                      type="button"
                      className="text-on-surface-variant hover:bg-surface-container px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                      onClick={() => {
                        setEditingCommentIndex(null);
                        setEditCommentNewText("");
                        setEditCommentErr(null);
                      }}
                    >
                      Hủy
                    </button>
                    <button
                      type="button"
                      className="bg-primary text-on-primary hover:bg-primary/90 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                      onClick={() => runEditComment(editingCommentIndex)}
                    >
                      Lưu thay đổi
                    </button>
                  </div>
                </div>
              </div>
            ) : null}

            <details className="group border-outline-variant bg-surface-container-low/20 mt-md rounded-xl border">
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

            <p className="text-on-surface-variant mt-md text-center text-[11px]">
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

    </Fragment>
  );
}
