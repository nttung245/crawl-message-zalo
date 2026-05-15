/**
 * KPI theo tuần lịch: **thứ Hai → chủ nhật** (tuần giao với tháng được liệt kê tuần 1…N).
 * Dùng cho nhãn UI, so khớp KPI và merge payload gửi `/kpi/assign`.
 */

export function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Ngày tại 00:00 local (tránh lệch so sánh). */
export function startOfLocalDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

export function toYmd(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

export type MonthWeekWindow = {
  year: number;
  month: number;
  /** 0-based: tuần đầu tiên (T2–CN) có giao với tháng = 0 */
  weekIndex: number;
  /** Thứ Hai tuần chứa `ref` (YYYY-MM-DD) */
  startYmd: string;
  /** Chủ nhật cùng tuần (YYYY-MM-DD) */
  endYmd: string;
  labelVi: string;
};

/** Thứ Hai của tuần chứa `d` (tuần: thứ Hai → chủ nhật). */
export function getMondayOfWeekContaining(d: Date): Date {
  const x = startOfLocalDay(d);
  const dow = x.getDay(); // 0 = CN, 1 = T2, …
  const offset = dow === 0 ? -6 : 1 - dow;
  x.setDate(x.getDate() + offset);
  return x;
}

/** Chủ nhật của tuần bắt đầu bằng thứ Hai `monday`. */
export function getSundayFromMonday(monday: Date): Date {
  const x = startOfLocalDay(monday);
  x.setDate(x.getDate() + 6);
  return x;
}

function dateLTE(a: Date, b: Date): boolean {
  return a.getTime() <= b.getTime();
}

function dateGTE(a: Date, b: Date): boolean {
  return a.getTime() >= b.getTime();
}

/**
 * Liệt kê các tuần (T2–CN) có **giao** với tháng `monthIndex0` (0 = tháng 1),
 * theo thứ tự thời gian. Tuần đầu có thể bắt đầu trước ngày 1 nhưng chủ nhật vẫn trong / sau ngày 1.
 */
export function listMondaySundayWeeksOverlappingMonth(
  year: number,
  monthIndex0: number,
): { mon: Date; sun: Date }[] {
  const monthStart = startOfLocalDay(new Date(year, monthIndex0, 1));
  const monthEnd = startOfLocalDay(new Date(year, monthIndex0 + 1, 0));
  let mon = getMondayOfWeekContaining(monthStart);
  const weeks: { mon: Date; sun: Date }[] = [];

  while (dateLTE(mon, monthEnd)) {
    const sun = getSundayFromMonday(mon);
    if (dateGTE(sun, monthStart)) {
      weeks.push({ mon: startOfLocalDay(mon), sun: startOfLocalDay(sun) });
    }
    const next = startOfLocalDay(mon);
    next.setDate(next.getDate() + 7);
    mon = next;
  }
  return weeks;
}

/** Nhãn ngắn: "11–17/05/2026" hoặc vắt tháng nếu tuần cắt hai tháng. */
export function formatWeekRangeVi(mon: Date, sun: Date): string {
  if (mon.getFullYear() === sun.getFullYear() && mon.getMonth() === sun.getMonth()) {
    return `${pad2(mon.getDate())}–${pad2(sun.getDate())}/${pad2(mon.getMonth() + 1)}/${mon.getFullYear()}`;
  }
  return `${pad2(mon.getDate())}/${pad2(mon.getMonth() + 1)} – ${pad2(sun.getDate())}/${pad2(sun.getMonth() + 1)}/${sun.getFullYear()}`;
}

/**
 * Tuần (T2–CN) chứa ngày `ref`, nằm trong lịch các tuần giao tháng đó.
 * `startYmd` / `endYmd` = cả tuần T2–CN (dùng so khớp KPI với tuần lịch).
 */
export function getMonthWeekWindowContaining(ref: Date = new Date()): MonthWeekWindow {
  const y = ref.getFullYear();
  const m0 = ref.getMonth();
  const refDay = startOfLocalDay(ref);
  const weeks = listMondaySundayWeeksOverlappingMonth(y, m0);
  const idx = weeks.findIndex(({ mon, sun }) => dateGTE(refDay, mon) && dateLTE(refDay, sun));

  let mon: Date;
  let sun: Date;
  let weekIndex: number;

  if (idx >= 0) {
    mon = weeks[idx].mon;
    sun = weeks[idx].sun;
    weekIndex = idx;
  } else {
    mon = getMondayOfWeekContaining(refDay);
    sun = getSundayFromMonday(mon);
    weekIndex = 0;
  }

  const startYmd = toYmd(mon);
  const endYmd = toYmd(sun);
  const labelVi =
    idx >= 0
      ? `Tuần ${idx + 1} (${formatWeekRangeVi(mon, sun)})`
      : `Tuần (${formatWeekRangeVi(mon, sun)})`;

  return {
    year: y,
    month: m0 + 1,
    weekIndex,
    startYmd,
    endYmd,
    labelVi,
  };
}

/** Một lựa chọn tuần T2–CN cho UI (leader xem KPI theo tuần). */
export type WeekPickerOption = {
  startYmd: string;
  endYmd: string;
  labelVi: string;
};

/**
 * Các tuần (T2–CN) trong các tháng quanh ``ref`` — không trùng khoảng ngày.
 * Dùng cho dropdown chọn tuần khi xem KPI.
 */
export function buildWeekPickerOptionsAroundDate(
  ref: Date = new Date(),
  monthsBack = 2,
  monthsForward = 2,
): WeekPickerOption[] {
  const seen = new Set<string>();
  const out: WeekPickerOption[] = [];
  const y0 = ref.getFullYear();
  const m0 = ref.getMonth();
  for (let offset = -monthsBack; offset <= monthsForward; offset += 1) {
    const dt = new Date(y0, m0 + offset, 1);
    const weeks = listMondaySundayWeeksOverlappingMonth(dt.getFullYear(), dt.getMonth());
    let wi = 0;
    for (const { mon, sun } of weeks) {
      wi += 1;
      const startYmd = toYmd(mon);
      const endYmd = toYmd(sun);
      const key = `${startYmd}|${endYmd}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const range = formatWeekRangeVi(mon, sun);
      out.push({
        startYmd,
        endYmd,
        labelVi: `Tuần ${wi} · T${dt.getMonth() + 1}/${dt.getFullYear()} (${range})`,
      });
    }
  }
  out.sort((a, b) => a.startYmd.localeCompare(b.startYmd));
  return out;
}

/** Hai khoảng ngày YYYY-MM-DD giao nhau (biên inclusive). */
export function rangesOverlap(
  aStart: string,
  aEnd: string,
  bStart: string,
  bEnd: string,
): boolean {
  const as = aStart.trim().slice(0, 10);
  const ae = aEnd.trim().slice(0, 10);
  const bs = bStart.trim().slice(0, 10);
  const be = bEnd.trim().slice(0, 10);
  if (!as || !ae || !bs || !be) return false;
  return !(ae < bs || as > be);
}

export type NormalizedKpiEntry = {
  start_day: string;
  end_day: string;
  total_session_crawl: number;
  total_post_crawl: number;
  total_comment: number;
  total_reaction: number;
};

function num(v: unknown): number {
  const n = Number(v);
  if (Number.isFinite(n)) return n;
  const p = parseInt(String(v ?? 0), 10);
  return Number.isFinite(p) ? p : 0;
}

export function normalizeKpiEntry(raw: unknown): NormalizedKpiEntry | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const sd = String(o.start_day ?? o.startDay ?? "").trim().slice(0, 10);
  const ed = String(o.end_day ?? o.endDay ?? "").trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(sd) || !/^\d{4}-\d{2}-\d{2}$/.test(ed)) return null;
  return {
    start_day: sd,
    end_day: ed,
    total_session_crawl: num(o.total_session_crawl ?? o.totalSessionCrawl ?? o.sessions),
    total_post_crawl: num(o.total_post_crawl ?? o.totalPostCrawl ?? o.posts),
    total_comment: num(o.total_comment ?? o.totalComment ?? o.comments),
    total_reaction: num(o.total_reaction ?? o.totalReaction ?? o.reactions),
  };
}

export function normalizeKpiList(raw: unknown): NormalizedKpiEntry[] {
  if (!Array.isArray(raw)) return [];
  const out: NormalizedKpiEntry[] = [];
  for (const item of raw) {
    const n = normalizeKpiEntry(item);
    if (n) out.push(n);
  }
  return out;
}

/** KPI có khoảng ngày giao với cửa sổ tuần T2–CN (`startYmd`/`endYmd`). */
export function findKpiOverlappingWindow(
  kpiList: unknown[],
  win: Pick<MonthWeekWindow, "startYmd" | "endYmd">,
): NormalizedKpiEntry | null {
  for (const raw of kpiList) {
    const e = normalizeKpiEntry(raw);
    if (!e) continue;
    if (rangesOverlap(e.start_day, e.end_day, win.startYmd, win.endYmd)) return e;
  }
  return null;
}

export function hasKpiForCurrentMonthWeek(
  kpiList: unknown[],
  ref: Date = new Date(),
): boolean {
  const win = getMonthWeekWindowContaining(ref);
  return findKpiOverlappingWindow(kpiList, win) !== null;
}

/**
 * Gửi lại toàn bộ mảng KPI: giữ các mục không giao tuần hiện tại, thay/thêm mục trong tuần T2–CN đó.
 */
export function mergeKpiPayload(
  sheetKpi: unknown[],
  win: Pick<MonthWeekWindow, "startYmd" | "endYmd">,
  updated: NormalizedKpiEntry,
): NormalizedKpiEntry[] {
  const existing = normalizeKpiList(sheetKpi);
  const rest = existing.filter(
    (e) => !rangesOverlap(e.start_day, e.end_day, win.startYmd, win.endYmd),
  );
  const next = [...rest, updated];
  next.sort((a, b) => a.start_day.localeCompare(b.start_day));
  return next;
}
