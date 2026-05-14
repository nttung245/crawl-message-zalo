import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner"; // Hoặc thư viện toast bạn đang dùng
import { createGroupService } from "../services/createGroupsService";
import { CreateGroupPayload } from "../schemas/create_groups_shemas";

export function useCreateGroup() {
    const router = useRouter();
    const [isLoading, setIsLoading] = useState(false);

    // Thêm return type hoặc để TypeScript tự suy luận
    const submitGroupData = async (data: CreateGroupPayload) => {
        setIsLoading(true);
        try {
            const result = await createGroupService(data);
            
            if (result.success==="success") {
                toast.success("Tạo Group thành công!");
                // Trả về dữ liệu từ API để Component sử dụng (nếu cần)
                return result.data;
            } else {
                toast.error(result.message || "Có lỗi xảy ra khi tạo group!");
                return null;
            }
        } catch (error) {
            toast.error("Có lỗi xảy ra khi kết nối đến server!");
         
            return null;
        } finally {
            setIsLoading(false);
        }
    };

    const handleCancel = () => {
        router.back();
    };

    return {
        isLoading,
        submitGroupData,
        handleCancel
    };
}