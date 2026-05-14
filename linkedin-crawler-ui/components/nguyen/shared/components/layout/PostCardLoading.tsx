// components/PostCardSkeleton.tsx
export const PostCardSkeleton = () => (
  <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100 animate-pulse">
    <div className="flex justify-between mb-4">
      <div className="h-4 bg-slate-200 rounded w-1/3" />
      <div className="h-4 bg-slate-200 rounded w-1/4" />
    </div>
    <div className="space-y-3">
      <div className="h-4 bg-slate-200 rounded w-full" />
      <div className="h-4 bg-slate-200 rounded w-5/6" />
    </div>
    <div className="mt-6 flex gap-2">
      <div className="h-20 bg-slate-200 rounded w-full" />
    </div>
  </div>
);