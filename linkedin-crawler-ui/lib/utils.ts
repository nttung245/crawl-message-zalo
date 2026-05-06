/**
 * Gộp className (chuẩn dự án — có thể nâng cấp clsx + tailwind-merge sau).
 */
export function cn(
  ...parts: Array<string | undefined | null | false>
): string {
  return parts.filter(Boolean).join(" ");
}
