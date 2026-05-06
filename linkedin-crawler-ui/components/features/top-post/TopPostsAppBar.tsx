"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { MaterialIcon } from "@/components/ui";
import { cn } from "@/lib/utils";

import { TOP_POST_HEADER_AVATAR } from "./constants";

const navActive =
  "cursor-pointer border-b-2 border-sky-700 pb-1 font-sans text-sm font-medium text-sky-700 opacity-90 transition-colors hover:opacity-100 dark:border-sky-400 dark:text-sky-400";
const navIdle =
  "cursor-pointer font-sans text-sm font-medium text-slate-600 opacity-90 transition-colors hover:text-sky-600 hover:opacity-100 dark:text-zinc-400 dark:hover:text-sky-300";

export function TopPostsAppBar() {
  const pathname = usePathname();
  const isHome = pathname === "/";
  const isTopPost = pathname.startsWith("/top-post");

  return (
    <header className="sticky top-0 z-50 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white px-6 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center gap-8">
        <Link
          href="/"
          className="text-xl font-bold tracking-tight text-sky-700 dark:text-sky-500"
        >
          CrawlerPro
        </Link>
        <nav className="hidden items-center gap-6 md:flex">
          <Link href="/" className={cn(isHome ? navActive : navIdle)}>
            Tổng quan
          </Link>
          <Link href="/top-post" className={cn(isTopPost ? navActive : navIdle)}>
            Top bài
          </Link>
          <span className="cursor-pointer font-sans text-sm font-medium text-slate-600 opacity-90 transition-colors hover:text-sky-600 hover:opacity-100 dark:text-zinc-400 dark:hover:text-sky-300">
            Lịch sử
          </span>
          <span className="cursor-pointer font-sans text-sm font-medium text-slate-600 opacity-90 transition-colors hover:text-sky-600 hover:opacity-100 dark:text-zinc-400 dark:hover:text-sky-300">
            Lịch chạy
          </span>
          <span className="cursor-pointer font-sans text-sm font-medium text-slate-600 opacity-90 transition-colors hover:text-sky-600 hover:opacity-100 dark:text-zinc-400 dark:hover:text-sky-300">
            Tài liệu
          </span>
        </nav>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative hidden sm:block">
          <MaterialIcon
            name="search"
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm text-slate-400"
          />
          <input
            className="border-outline-variant bg-surface-container-low focus:ring-primary-container w-64 rounded-lg border py-1.5 pr-4 pl-10 text-sm focus:ring-1 focus:outline-none"
            placeholder="Tìm crawler..."
            type="search"
            aria-label="Tìm crawler"
          />
        </div>
        <button
          type="button"
          className="text-slate-600 hover:text-sky-600 dark:text-zinc-400"
          aria-label="Thông báo"
        >
          <MaterialIcon name="notifications" />
        </button>
        <button
          type="button"
          className="text-slate-600 hover:text-sky-600 dark:text-zinc-400"
          aria-label="Cài đặt"
        >
          <MaterialIcon name="settings" />
        </button>
        <div className="h-8 w-8 overflow-hidden rounded-full border border-slate-200">
          <Image
            src={TOP_POST_HEADER_AVATAR}
            alt="Ảnh hồ sơ"
            width={32}
            height={32}
            className="h-full w-full object-cover"
          />
        </div>
      </div>
    </header>
  );
}
