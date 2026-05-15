"use client";

import { useAppPlatform } from "@/components/providers/AppPlatformProvider";
import {
  APP_PLATFORM_LABEL,
  type AppPlatform,
} from "@/lib/LinkedIn-app-platform";
import { cn } from "@/lib/utils";

const options: AppPlatform[] = ["linkedin", "facebook"];

export function DashboardPlatformSwitcher() {
  const { platform, setPlatform } = useAppPlatform();

  return (
    <div className="mb-4 px-2">
      <p className="text-on-surface-variant mb-2 px-2 font-sans text-[10px] font-bold tracking-wider uppercase">
        Nền tảng
      </p>
      <div
        className="border-outline-variant bg-surface-container-low flex rounded-lg border p-0.5"
        role="group"
        aria-label="Chọn nền tảng crawler"
      >
        {options.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPlatform(p)}
            className={cn(
              "flex-1 rounded-md px-2 py-2 font-sans text-[10px] font-bold tracking-wide uppercase transition-colors",
              platform === p
                ? "bg-primary text-on-primary shadow-sm"
                : "text-on-surface-variant hover:bg-surface-container-high/80",
            )}
          >
            {APP_PLATFORM_LABEL[p]}
          </button>
        ))}
      </div>
    </div>
  );
}
