export type AppPlatform = "linkedin" | "facebook";

export const APP_PLATFORM_STORAGE_KEY = "crawlerpro-app-platform";

export function isAppPlatform(value: string | null | undefined): value is AppPlatform {
  return value === "linkedin" || value === "facebook";
}

export const APP_PLATFORM_LABEL: Record<AppPlatform, string> = {
  linkedin: "LinkedIn",
  facebook: "Facebook",
};
