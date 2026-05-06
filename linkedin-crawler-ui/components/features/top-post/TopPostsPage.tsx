"use client";

import { useMemo, useState } from "react";

import { MaterialIcon } from "@/components/ui";

import {
  TOP_POSTS_MOCK,
  TOP_POSTS_PAGE_SIZE,
  TOP_POSTS_TOTAL,
} from "./mockData";
import { TopPostCard } from "./TopPostCard";
import { TopPostsAppBar } from "./TopPostsAppBar";
import { TopPostsPagination } from "./TopPostsPagination";
import { TopPostsSidebar } from "./TopPostsSidebar";
import { TopPostsStatsRow } from "./TopPostsStatsRow";

const TOTAL_PAGES = Math.max(
  1,
  Math.ceil(TOP_POSTS_TOTAL / TOP_POSTS_PAGE_SIZE),
);

export function TopPostsPage() {
  const [page, setPage] = useState(1);

  const { pageStart, pageEnd, slice } = useMemo(() => {
    const start = (page - 1) * TOP_POSTS_PAGE_SIZE;
    const end = Math.min(start + TOP_POSTS_PAGE_SIZE, TOP_POSTS_TOTAL);
    const sliceLocal = TOP_POSTS_MOCK.slice(start, end);
    return {
      pageStart: TOP_POSTS_TOTAL === 0 ? 0 : start + 1,
      pageEnd: end,
      slice: sliceLocal,
    };
  }, [page]);

  const handlePrev = () => setPage((p) => Math.max(1, p - 1));
  const handleNext = () => setPage((p) => Math.min(TOTAL_PAGES, p + 1));
  const handleSelect = (p: number) =>
    setPage(Math.min(Math.max(1, p), TOTAL_PAGES));

  return (
    <div className="page-canvas-brand font-body-md text-on-surface min-h-screen">
      <TopPostsAppBar />
      <TopPostsSidebar />

      <main className="min-h-screen px-lg pt-lg pb-xl lg:ml-64">
        <div className="mx-auto max-w-[1440px]">
          <div className="mb-xl flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <div>
              <h1 className="font-h1 text-h1 text-on-surface mb-xs">
                Các bài viết có lượng tương tác cao
              </h1>
              <p className="font-body-md text-on-surface-variant max-w-2xl">
                Tổng hợp nội dung hiệu quả từ 14 nhóm LinkedIn. Phân tích dựa
                trên tốc độ tương tác và mức độ cảm xúc trong 24 giờ qua.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                className="border-outline-variant text-primary font-label-md flex items-center gap-2 rounded border bg-white px-md py-xs shadow-sm transition-all hover:bg-surface-container"
              >
                <MaterialIcon name="filter_list" className="text-[18px]" />
                Lọc
              </button>
              <button
                type="button"
                className="bg-primary-container font-label-md flex items-center gap-2 rounded px-lg py-xs text-white shadow-sm transition-all hover:brightness-110"
              >
                <MaterialIcon name="table_view" className="text-[18px]" />
                Xem bảng dữ liệu đầy đủ
              </button>
            </div>
          </div>

          <TopPostsStatsRow />

          <div className="grid grid-cols-1 gap-lg md:grid-cols-2 xl:grid-cols-3">
            {slice.map((post) => (
              <TopPostCard key={post.id} post={post} />
            ))}
          </div>

          <TopPostsPagination
            page={page}
            totalPages={TOTAL_PAGES}
            pageStart={pageStart}
            pageEnd={pageEnd}
            totalItems={TOP_POSTS_TOTAL}
            onPrev={handlePrev}
            onNext={handleNext}
            onSelectPage={handleSelect}
          />
        </div>
      </main>
    </div>
  );
}
