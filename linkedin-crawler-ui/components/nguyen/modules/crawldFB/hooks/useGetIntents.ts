import { useState, useCallback } from "react";
import { getIntentsService } from "../services/intent_service";
import { IntentItemDTO } from "../schemas/intent_schemas";

export const useGetIntents = () => {
  const [intents, setIntents] = useState<IntentItemDTO[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Dùng useCallback để tránh hàm bị tạo lại vô cớ mỗi khi component re-render
  const fetchIntents = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const data = await getIntentsService();
      setIntents(data);
      setIsLoading(false);
      return data;
    } catch (error: any) {
      setIsLoading(false);
      const errorMsg = error?.response?.data?.message || "Lỗi tải danh sách Intent.";
      setErrorMessage(errorMsg);
      // Trả về mảng rỗng nếu lỗi để ứng dụng không bị crash
      return [];
    }
  }, []);

  return {
    intents,
    // Hỗ trợ hàm set thẳng state nội bộ để UI có thể tự chèn thêm intent mới tạo vào mảng
    setIntents, 
    isLoading,
    errorMessage,
    fetchIntents,
  };
};