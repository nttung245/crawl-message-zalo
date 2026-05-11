"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { MaterialIcon } from "@/components/ui";
import { cn } from "@/lib/utils";

const sideActive =
  "border-sky-700 bg-slate-50 text-sky-700 flex items-center gap-3 border-r-4 py-3 pr-5 pl-6 transition-all duration-150 active:scale-95 dark:border-sky-400 dark:bg-zinc-800/50 dark:text-sky-400";
const sideIdle =
  "flex items-center gap-3 px-6 py-3 text-slate-500 transition-all duration-150 hover:bg-slate-50 hover:text-sky-600 active:scale-95 dark:text-zinc-400 dark:hover:bg-zinc-800/50 dark:hover:text-sky-300";

export function LinkedInTopPostsSidebar() {
  const pathname = usePathname();
  const isHome = pathname === "/";
  const isTopPost = pathname.startsWith("/top-post");
  const isGroupMgmt = pathname === "/quan-ly-nhom";

  return (
    <aside className="fixed top-0 left-0 z-40 hidden h-screen w-64 flex-col border-r border-slate-200 bg-white pt-20 lg:flex dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-8 flex items-center gap-3 px-6">
        <div className="bg-primary-container flex h-10 w-10 shrink-0 items-center justify-center rounded text-white">
          <MaterialIcon name="analytics" />
        </div>
        <div>
          <h2 className="text-lg leading-tight font-black text-slate-900 dark:text-zinc-100">
            LinkedIn Scraper
          </h2>
        </div>
      </div>
      <nav className="flex-1 space-y-1">
        <Link href="/" className={cn(isHome ? sideActive : sideIdle)}>
          <MaterialIcon name="radar" className="shrink-0" />
          <span className="font-sans text-xs font-bold tracking-wider uppercase">
            Post Feed
          </span>
        </Link>
       
        
        <Link
          href="/quan-ly-nhom"
          className={cn(isGroupMgmt ? sideActive : sideIdle)}
        >
          <MaterialIcon name="group" className="shrink-0" />
          <span className="font-sans text-xs font-bold tracking-wider uppercase">
            GROUP
          </span>
        </Link>
        
       
      </nav>
      <div className="border-slate-100 p-6 dark:border-zinc-800">
        <button
          type="button"
          className="bg-primary-container hover:bg-primary mb-6 w-full rounded py-2 text-xs font-bold tracking-widest text-white uppercase transition-colors"
        >
          Crawl mới
        </button>
        <div className="space-y-1">
          <span className="text-slate-500 hover:text-sky-600 flex cursor-pointer items-center gap-3 py-2 transition-colors">
            <MaterialIcon name="help" className="text-sm" />
            <span className="text-xs font-bold tracking-wider uppercase">
              Trợ giúp
            </span>
          </span>
          <span className="text-slate-500 hover:text-sky-600 flex cursor-pointer items-center gap-3 py-2 transition-colors">
            <MaterialIcon name="account_circle" className="text-sm" />
            <span className="text-xs font-bold tracking-wider uppercase">
              Tài khoản
            </span>
          </span>
        </div>
      </div>
    </aside>
  );
}
