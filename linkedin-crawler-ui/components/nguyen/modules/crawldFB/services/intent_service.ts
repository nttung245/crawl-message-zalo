// src/modules/intent/services/intent.service.ts
import axiosClient from "../../../shared/api/axiosClient";
import { CreateBatchIntentsDTO } from "../schemas/intent_schemas";

export const createBatchIntentsService = async (payload: CreateBatchIntentsDTO) => {
  // Gửi mảng payload.intents thẳng lên API xử lý insert nhiều dòng
  const response = await axiosClient.post("/api/v1/intents/bulk-add", payload);
  return response.data;
};
import { IntentItemDTO } from "../schemas/intent_schemas";
export interface GetIntentsResponse {
  status: string;
  message: string;
  data: IntentItemDTO[]; 
}
export const getIntentsService = async (): Promise<IntentItemDTO[]> => {
  const response = await axiosClient.get<GetIntentsResponse>("/api/v1/intents");
  
  // Tùy thuộc vào cách backend bọc dữ liệu, ở đây giả sử lấy response.data.data
  return response.data.data;
};