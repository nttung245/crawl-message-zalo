interface LoadingProps {
  title?: string;
  content?: string;
  onCancel?: () => void;
}

export default function FullScreenLoading({
  title = "Đang xử lý dữ liệu",
  content = "Hệ thống đang tải và xử lý thông tin, vui lòng chờ trong giây lát...",
  onCancel,
}: LoadingProps) {
  return (
    <div className="w-full min-h-screen fixed inset-0 flex items-center justify-center bg-slate-200/30 backdrop-blur-sm z-50">
      <div className="bg-white shadow-2xl rounded-3xl p-10 max-w-md w-full border border-slate-200 text-center">
        <div className="flex justify-center mb-6">
          <div className="w-16 h-16 border-4 border-violet-200 border-t-violet-600 rounded-full animate-spin" />
        </div>

        <h1 className="text-2xl font-bold text-slate-800 mb-3">{title}</h1>
        <p className="text-slate-500 leading-7 text-sm">{content}</p>

        {onCancel && (
          <button
            onClick={onCancel}
            className="mt-6 px-6 py-2 bg-red-50 text-red-600 hover:bg-red-100 font-semibold rounded-lg transition-colors"
          >
            Hủy tiến trình
          </button>
        )}
      </div>
    </div>
  );
}
