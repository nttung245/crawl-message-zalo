import axiosClient from "../../../shared/api/axiosClient";
import { CreateGroupPayload } from "../schemas/create_groups_shemas";

// Định nghĩa kiểu dữ liệu trả về từ API (Response) - Bạn có thể tùy chỉnh lại theo đúng thực tế Backend trả về
export interface CreateGroupResponse {
    success: "success" | "error";
    message: string;
    data?: any; 
}

export const createGroupService = async (payload: CreateGroupPayload): Promise<CreateGroupResponse> => {
    // Thay "/groups" bằng đúng endpoint API của bạn
    console.log("payload",payload);
    
    const response = await axiosClient.post<CreateGroupResponse>("/api/v1/groups/bulk-add", { groups: [payload] });
    return response.data;
};