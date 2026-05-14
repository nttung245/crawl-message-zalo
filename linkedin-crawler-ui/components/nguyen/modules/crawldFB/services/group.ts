// src/modules/group/services/group.service.ts
import axiosClient from "../../../shared/api/axiosClient";
import { FacebookGroupDTO } from "../types/dataFb.type";

// Định nghĩa Interface cho cấu trúc bọc (Wrapper) của Backend trả về
export interface GetPresetGroupsResponse {
    status: string;
    data: FacebookGroupDTO[];
}

/**
 * Gọi API lấy danh sách các Facebook Group có sẵn (Preset)
 * @returns Promise chứa mảng FacebookGroupDTO
 */
export const getPresetGroupsService = async (): Promise<FacebookGroupDTO[]> => {
    // Truyền kiểu bọc dữ liệu vào generic của axiosClient
    const response = await axiosClient.get<GetPresetGroupsResponse>("/api/v1/groups");
    
    // Trả về trực tiếp mảng dữ liệu bên trong, đảm bảo an toàn với fallback mảng rỗng
    return response.data.data || [];
};