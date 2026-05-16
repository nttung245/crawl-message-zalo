import { z } from "zod";

export const InteractionSchema = z.object({
    url: z.string().min(1, "Thiếu URL bài viết"),
    id: z.string().min(1, "Vui lòng chọn người dùng"),
    reaction: z.string().min(1, "Vui lòng chọn cảm xúc"),
    comment: z.string().optional(),
    name: z.string().optional(),
});

export type InteractionPayload = z.infer<typeof InteractionSchema>;

export const initialInteractionData: InteractionPayload = {
    url: "",
    id: "",
    reaction: "LIKE",
    comment: "",
    name: "",
};