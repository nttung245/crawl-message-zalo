import { z } from "zod";


export const CreateGroupSchema = z.object({
    group_name: z.string().min(1, "Vui lòng nhập tên hiển thị Group"),
    link_group: z.string()
        .min(1, "Vui lòng nhập Link URL")
        .url("Đường dẫn URL không hợp lệ"),
    intent: z.string().min(1, "Vui lòng chọn mục đích (Intent)"),
    members: z.coerce.number().int().optional(),
    posts_per_week: z.string().optional(),
    chay_24h: z.boolean().default(false),
    health_score:z.coerce.number().int().optional(),
});

// Xuất type tự động từ Zod Schema để dùng cho các file khác
export type CreateGroupPayload = z.infer<typeof CreateGroupSchema>;

export const initialCreateGroupData: CreateGroupPayload = {
    group_name: "",
    link_group: "",
    intent: "",
    members: 0,
    posts_per_week: "0",
    chay_24h: false,
    health_score: 0,
};