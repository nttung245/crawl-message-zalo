// src/modules/group/hooks/useGetPresetGroups.ts
import { useState, useCallback } from "react";
import { FacebookGroupDTO } from "../types/dataFb.type";
import { getPresetGroupsService } from "../services/group"; // ✅ Import Service thuần

export const useGetPresetGroups = () => {
    const [presetGroups, setPresetGroups] = useState<FacebookGroupDTO[]>([]);
    const [isLoadingGroups, setIsLoadingGroups] = useState<boolean>(false);
    const [errorGroups, setErrorGroups] = useState<string | null>(null);

    const fetchPresetGroups = useCallback(async () => {
        setIsLoadingGroups(true);
        setErrorGroups(null);

        try {
            // ✅ Gọi tầng Service xử lý data thay vì viết Axios trực tiếp ở đây
            const data = await getPresetGroupsService();
            console.log(data);
            
            setPresetGroups(data);
            setIsLoadingGroups(false);
            return data;
        } catch (error: any) {
            setIsLoadingGroups(false);
            // Trích xuất lỗi chuẩn từ Axios bọc lại cho UI hiển thị
            const errorMsg = error?.response?.data?.message || "Lỗi tải danh sách Facebook Group.";
            setErrorGroups(errorMsg);
            return [];
        }
    }, []);

    return {
        presetGroups,
        isLoadingGroups,
        errorGroups,
        fetchPresetGroups,
    };
};