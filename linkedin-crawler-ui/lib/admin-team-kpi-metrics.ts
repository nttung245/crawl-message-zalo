/**
 * Đếm thực tế phiên / bài / comment / tương tác cho **một** email_crawl trong khoảng ngày,
 * khớp logic member dashboard (dedupe theo email+URL bài, ngày comment / ngày tương tác).
 */

import type { CrawlSessionGroup } from "@/types/api";
import {
  pickPostUrlFromRecord,
  pickStr,
  sessionLatestDateLabel,
} from "@/components/features/dashboard/n8n-sheet-helpers";
import { appCommentDay, parseAppCommentsFromPost } from "@/lib/LinkedIn-appComments";
import { parseSheetReaction } from "@/components/features/linkedin/dashboard/LinkedIn-post-sheet-engagement";

export type MemberKpiActuals = {
  sessions: number;
  posts: number;
  comments: number;
  interactions: number;
};

export function ymdInInclusiveRange(ymd: string, startDay: string, endDay: string): boolean {
  const d = ymd.trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return false;
  if (startDay && d < startDay) return false;
  if (endDay && d > endDay) return false;
  return true;
}

export function postRepresentativeYmd(post: Record<string, unknown>): string {
  const fromNgay = pickStr(post, ["Ngày", "date", "targetDate"]).slice(0, 10).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(fromNgay)) return fromNgay;
  const raw = pickStr(post, ["Đăng vào", "posted_at", "created_at"]);
  if (raw.length >= 10) {
    const head = raw.slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(head)) return head;
  }
  return "";
}

/**
 * @param memberEmail — chỉ tính phiên có ``email_crawl`` trùng email này (email member cào, không phải email leader).
 * @param allSessions — nên là dataset đã gộp đủ phiên của các member (leader: gọi get-all-posts theo từng email member rồi merge).
 */
export function computeMemberActualsInYmdRange(
  memberEmail: string,
  allSessions: CrawlSessionGroup[] | null | undefined,
  rangeStart: string,
  rangeEnd: string,
): MemberKpiActuals {
  const zeros: MemberKpiActuals = { sessions: 0, posts: 0, comments: 0, interactions: 0 };
  const em = memberEmail.trim().toLowerCase();
  if (!em || !allSessions?.length) return zeros;

  const stats = { ...zeros };
  const countedPostKeys = new Set<string>();
  const commentKeys = new Set<string>();
  const interactionKeys = new Set<string>();

  for (const session of allSessions) {
    const emailKey = String(session.email_crawl ?? "").trim().toLowerCase();
    if (emailKey !== em) continue;

    const sDate = sessionLatestDateLabel(session);
    if (sDate === "—") continue;
    if (!ymdInInclusiveRange(sDate, rangeStart, rangeEnd)) continue;

    stats.sessions += 1;

    const posts = Array.isArray(session.posts) ? session.posts : [];
    for (let pi = 0; pi < posts.length; pi++) {
      const p = posts[pi] as Record<string, unknown>;
      const postYmd = postRepresentativeYmd(p) || sDate;
      if (!ymdInInclusiveRange(postYmd, rangeStart, rangeEnd)) continue;

      const urlKey =
        pickPostUrlFromRecord(p).trim().toLowerCase() ||
        `sid:${String(session.id_session_crawl ?? "").trim()}:p${pi}`;
      const dedupeKey = `${em}::${urlKey}`;

      if (!countedPostKeys.has(dedupeKey)) {
        countedPostKeys.add(dedupeKey);
        stats.posts += 1;
      }

      const hasCommentInWeek = parseAppCommentsFromPost(p).some((entry) => {
        const cd = appCommentDay(entry).trim().slice(0, 10);
        return ymdInInclusiveRange(cd, rangeStart, rangeEnd);
      });
      if (hasCommentInWeek && !commentKeys.has(dedupeKey)) {
        commentKeys.add(dedupeKey);
        stats.comments += 1;
      }

      const { kind, triggerDay } = parseSheetReaction(p);
      if (kind && !interactionKeys.has(dedupeKey)) {
        let iday = triggerDay.trim().slice(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(iday)) {
          iday = postYmd;
        }
        if (ymdInInclusiveRange(iday, rangeStart, rangeEnd)) {
          interactionKeys.add(dedupeKey);
          stats.interactions += 1;
        }
      }
    }
  }

  return stats;
}

/** Tổng actuals của nhiều member: mỗi email là ``email_crawl`` trên phiên (không dùng email leader để lọc). */
export function computeTeamActualsSumInYmdRange(
  memberEmails: readonly string[],
  allSessions: CrawlSessionGroup[] | null | undefined,
  rangeStart: string,
  rangeEnd: string,
): MemberKpiActuals {
  const sum: MemberKpiActuals = { sessions: 0, posts: 0, comments: 0, interactions: 0 };
  for (const e of memberEmails) {
    const a = computeMemberActualsInYmdRange(e, allSessions, rangeStart, rangeEnd);
    sum.sessions += a.sessions;
    sum.posts += a.posts;
    sum.comments += a.comments;
    sum.interactions += a.interactions;
  }
  return sum;
}
