"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  APP_PLATFORM_STORAGE_KEY,
  type AppPlatform,
  isAppPlatform,
} from "@/lib/LinkedIn-app-platform";

type AppPlatformContextValue = {
  platform: AppPlatform;
  setPlatform: (p: AppPlatform) => void;
};

const AppPlatformContext = createContext<AppPlatformContextValue | null>(null);

export function AppPlatformProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [platform, setPlatformState] = useState<AppPlatform>("linkedin");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(APP_PLATFORM_STORAGE_KEY);
      if (isAppPlatform(raw)) setPlatformState(raw);
    } catch {
      /* ignore */
    }
  }, []);

  const setPlatform = useCallback((p: AppPlatform) => {
    setPlatformState(p);
    try {
      localStorage.setItem(APP_PLATFORM_STORAGE_KEY, p);
    } catch {
      /* ignore */
    }
  }, []);

  const value = useMemo(
    () => ({ platform, setPlatform }),
    [platform, setPlatform],
  );

  return (
    <AppPlatformContext.Provider value={value}>
      {children}
    </AppPlatformContext.Provider>
  );
}

export function useAppPlatform(): AppPlatformContextValue {
  const ctx = useContext(AppPlatformContext);
  if (!ctx) {
    throw new Error("useAppPlatform must be used within AppPlatformProvider");
  }
  return ctx;
}
