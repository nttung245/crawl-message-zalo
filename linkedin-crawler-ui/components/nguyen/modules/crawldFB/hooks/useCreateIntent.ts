
import { useState } from "react";
import { createBatchIntentsService } from "../services/intent_service";
import { CreateBatchIntentsDTO } from "../schemas/intent_schemas";

export const useCreateBatchIntents = () => {
  // Quản lý các trạng thái nội bộ bằng useState thuần
  const [isPending, setIsPending] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  /**
   * Hàm xử lý tạo danh sách Intent
   * @param payload Dữ liệu mảng Intent gửi lên từ Form
   * @param options Callback hỗ trợ chạy các tác vụ phụ (như reset form) khi thành công
   */
  const mutate = async (
    payload: CreateBatchIntentsDTO,
    options?: { onSuccess?: () => void }
  ) => {
    // Đặt trạng thái ban đầu trước khi gọi API
    setIsPending(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      // Gọi service giao tiếp với Backend
      const res = await createBatchIntentsService(payload);

      // Xử lý thành công
      setIsPending(false);
      setSuccessMessage("Thêm danh sách Intent thành công!");
      
      // Kích hoạt callback từ UI Component (nếu có truyền vào)
      if (options?.onSuccess) {
        options.onSuccess();
      }

      return res;
    } catch (error: any) {
      // Xử lý thất bại và trích xuất thông báo lỗi từ Backend
      setIsPending(false);
      const errorMsg =
        error?.response?.data?.message || "Đã xảy ra lỗi khi tạo danh sách Intent";
      setErrorMessage(errorMsg);
    }
  };

  // Trả về giao diện chuẩn xác cho Component con sử dụng
  return {
    mutate,
    isPending,
    errorMessage,
    successMessage,
    // Hỗ trợ hàm clear thông báo để UI có thể chủ động đóng cảnh báo khi cần
    clearMessages: () => {
      setErrorMessage(null);
      setSuccessMessage(null);
    },
  };
};