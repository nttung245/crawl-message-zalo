/** Local calendar date YYYY-MM-DD (no timezone shift vs UTC conversion). */

export function pad2(n: number): string {
  return n < 10 ? `0${n}` : `${n}`;
}

export function localYmd(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

export function parseYmd(ymd: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const day = Number(m[3]);
  const out = new Date(y, mo, day);
  if (out.getFullYear() !== y || out.getMonth() !== mo || out.getDate() !== day) return null;
  return out;
}

export function addDaysLocal(base: Date, delta: number): Date {
  const d = new Date(base.getFullYear(), base.getMonth(), base.getDate());
  d.setDate(d.getDate() + delta);
  return d;
}

export function todayYmd(): string {
  return localYmd(new Date());
}

export function yesterdayYmd(): string {
  return localYmd(addDaysLocal(new Date(), -1));
}
