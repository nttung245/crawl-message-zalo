"use client";

interface LinkedInTopPostsPaginationProps {
  page: number;
  totalPages: number;
  pageStart: number;
  pageEnd: number;
  totalItems: number;
  onPrev: () => void;
  onNext: () => void;
  onSelectPage: (p: number) => void;
}

export function LinkedInTopPostsPagination({
  page,
  totalPages,
  pageStart,
  pageEnd,
  totalItems,
  onPrev,
  onNext,
  onSelectPage,
}: LinkedInTopPostsPaginationProps) {
  return (
    <div className="border-outline-variant mt-xl flex flex-col items-center justify-between gap-4 border-t py-md md:flex-row">
      <p className="text-body-sm text-on-surface-variant text-center md:text-left">
        Hiển thị{" "}
        <span className="text-on-surface font-bold">
          {pageStart}–{pageEnd}
        </span>{" "}
        trong tổng{" "}
        <span className="text-on-surface font-bold">
          {totalItems.toLocaleString("vi-VN")}
        </span>{" "}
        bài có tương tác cao
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        <button
          type="button"
          onClick={onPrev}
          disabled={page <= 1}
          className="border-outline-variant text-on-surface-variant hover:bg-white rounded border px-md py-1.5 font-label-md transition-colors disabled:opacity-40"
        >
          Trước
        </button>
        {Array.from(
          { length: Math.min(totalPages, 5) },
          (_, i) => i + 1,
        ).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onSelectPage(p)}
            className={`border-outline-variant rounded border px-md py-1.5 font-label-md transition-colors ${
              p === page
                ? "text-on-surface bg-white shadow-sm"
                : "text-on-surface-variant hover:bg-white"
            }`}
          >
            {p}
          </button>
        ))}
        <button
          type="button"
          onClick={onNext}
          disabled={page >= totalPages}
          className="border-outline-variant text-on-surface-variant hover:bg-white rounded border px-md py-1.5 font-label-md transition-colors disabled:opacity-40"
        >
          Tiếp
        </button>
      </div>
    </div>
  );
}
