// src/modules/intent/schemas/create-intents.schema.ts
import { z } from "zod";

// Khai báo schema cho 1 item Intent
const IntentItemSchema = z.object({
  name: z.string().trim().min(1, "Vui lòng nhập tên Intent (vd: Tuyển dụng)"),
  value: z.string().trim().min(1, "Vui lòng nhập giá trị Value (vd: recruitment)"),
});

// Schema tổng bọc lấy mảng các items
export const CreateBatchIntentsSchema = z.object({
  intents: z.array(IntentItemSchema).min(1, "Cần thêm ít nhất 1 Intent"),
});

// Xuất DTO và Form Types
export type CreateBatchIntentsDTO = z.infer<typeof CreateBatchIntentsSchema>;
export type IntentItemDTO = z.infer<typeof IntentItemSchema>;