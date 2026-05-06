"use client";

import Image from "next/image";

import { MaterialIcon } from "@/components/ui";

import { topPostStatusClass, topPostStatusLabel } from "./top-post-helpers";
import type { TopPost } from "./types";

interface TopPostCardProps {
  post: TopPost;
}

export function TopPostCard({ post }: TopPostCardProps) {
  return (
    <article className="enterprise-card group flex flex-col overflow-hidden rounded-xl">
      <div className="border-outline-variant flex items-start justify-between gap-3 border-b p-md">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="h-10 w-10 shrink-0 overflow-hidden rounded-full bg-slate-200">
            <Image
              src={post.avatarUrl}
              alt={post.authorName}
              width={40}
              height={40}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="min-w-0">
            <h3 className="font-h3 mb-1 truncate text-body-md leading-none font-semibold text-on-surface">
              {post.authorName}
            </h3>
            <p className="truncate text-body-sm text-on-surface-variant">
              {post.authorRole}
            </p>
          </div>
        </div>
        <span
          className={`shrink-0 rounded px-2 py-1 text-[10px] font-bold tracking-wide uppercase ${topPostStatusClass(post.status)}`}
        >
          {topPostStatusLabel(post.status)}
        </span>
      </div>

      <div className="border-outline-variant/80 bg-surface-container-low/60 flex items-start gap-2 border-b px-md py-sm">
        <MaterialIcon
          name="group"
          className="mt-0.5 shrink-0 text-[18px] text-primary"
        />
        <div className="min-w-0 text-body-sm">
          <span className="text-on-surface-variant font-semibold uppercase tracking-wide">
            Nguồn nhóm:{" "}
          </span>
          <a
            href={post.groupUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary font-medium underline-offset-2 hover:underline"
          >
            {post.groupName}
          </a>
        </div>
      </div>

      <div className="flex flex-1 flex-col p-md">
        <h2 className="text-h3 mb-sm line-clamp-2 font-semibold text-on-surface">
          {post.title}
        </h2>
        <p className="font-body-md text-on-surface line-clamp-4 leading-relaxed">
          {post.excerpt}
        </p>
        <a
          href={post.postUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary font-label-md mt-md inline-flex items-center gap-1 hover:underline"
        >
          Xem bài trên LinkedIn
          <MaterialIcon name="open_in_new" className="text-[14px]" />
        </a>
      </div>

      <div className="border-outline-variant bg-surface-container-low flex flex-wrap items-center justify-between gap-3 border-t p-md">
        <div className="flex flex-wrap gap-4">
          <div className="text-on-surface-variant flex items-center gap-1">
            <MaterialIcon name="thumb_up" className="text-[18px]" />
            <span className="font-label-md">{post.likesLabel}</span>
          </div>
          <div className="text-on-surface-variant flex items-center gap-1">
            <MaterialIcon name="comment" className="text-[18px]" />
            <span className="font-label-md">{post.commentsCount}</span>
          </div>
          <div className="text-on-surface-variant flex items-center gap-1">
            <MaterialIcon name="share" className="text-[18px]" />
            <span className="font-label-md">{post.sharesCount}</span>
          </div>
        </div>
        <div
          className="h-1 w-24 overflow-hidden rounded-full bg-slate-200"
          title={`Mức tương tác ước lượng: ${post.engagementPct}%`}
        >
          <div
            className="bg-primary-container h-full rounded-full transition-all"
            style={{ width: `${post.engagementPct}%` }}
          />
        </div>
      </div>
    </article>
  );
}
