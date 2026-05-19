import { cn } from "@/lib/utils";

export type MaterialSymbolName =
  | "search"
  | "notifications"
  | "settings"
  | "radar"
  | "download"
  | "group"
  | "list_alt"
  | "playlist_add"
  | "api"
  | "add"
  | "expand_less"
  | "expand_more"
  | "help"
  | "account_circle"
  | "person"
  | "shield_person"
  | "error"
  | "settings_input_component"
  | "monitoring"
  | "file_download"
  | "code"
  | "refresh"
  | "visibility"
  | "chevron_left"
  | "chevron_right"
  | "group_add"
  | "person_add"
  | "calendar_month"
  | "assignment"
  | "speed"
  | "database"
  | "analytics"
  | "trending_up"
  | "filter_list"
  | "table_view"
  | "open_in_new"
  | "thumb_up"
  | "favorite"
  | "celebration"
  | "volunteer_activism"
  | "lightbulb"
  | "sentiment_very_satisfied"
  | "comment"
  | "share"
  | "arrow_upward"
  | "check_circle"
  | "info"
  | "tune"
  | "close"
  | "lock"
  | "block"
  | "verified_user"
  | "filter_alt_off"
  | "edit"
  | "delete"
  | "sync"
  | "article"
  | "more_vert"
  | "chat_bubble"
  | "history";

export interface MaterialIconProps {
  name: MaterialSymbolName;
  className?: string;
  /** FILL=1 (ví dụ icon check tròn đặc) */
  filled?: boolean;
  "aria-hidden"?: boolean;
}

/**
 * Icon Material Symbols — cần font "Material Symbols Outlined"
 * (load trong layout + class `.material-symbols-outlined` trong globals.css).
 */
const OUTLINED_VAR =
  "'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24" as const;
const FILLED_VAR =
  "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 24" as const;

export function MaterialIcon({
  name,
  className,
  filled = false,
  "aria-hidden": ariaHidden = true,
}: MaterialIconProps) {
  return (
    <span
      className={cn("material-symbols-outlined", className)}
      style={{ fontVariationSettings: filled ? FILLED_VAR : OUTLINED_VAR }}
      aria-hidden={ariaHidden}
    >
      {name}
    </span>
  );
}
