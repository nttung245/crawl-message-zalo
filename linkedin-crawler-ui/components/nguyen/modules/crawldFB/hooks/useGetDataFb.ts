import { useState, useEffect } from 'react';
import { getDataFbService } from '../services/getDataFacebook';
import { DataFBResponse } from '../types/dataFb.type';
export const useFetchAllPosts = () => {
    // Lưu trữ toàn bộ dữ liệu trả về
    const [allPosts, setAllPosts] = useState<DataFBResponse[]>([]);
    // Trạng thái loading
    const [isLoading, setIsLoading] = useState<boolean>(true);
    // Trạng thái lỗi (nếu có)
    const [error, setError] = useState<string | null>(null);

    const fetchAllData = async () => {
        setIsLoading(true);
        setError(null);
        try {
            // Thay URL này bằng endpoint API thực tế của bạn
            const response = await getDataFbService()
            // Lưu ý: Tuỳ thuộc vào backend trả về trực tiếp mảng hay bọc trong object.
            // Ví dụ backend trả [{}, {}] thì dùng: response.data
            // Nếu backend trả { data: [{}, {}] } thì dùng: response.data.data
            console.log(response);
            
            setAllPosts(response.data); 
            
        } catch (err) {
            console.error("Lỗi khi lấy dữ liệu bằng axios:", err);
            setError("Không thể tải dữ liệu từ máy chủ.");
            setAllPosts([]); // Đảm bảo trả về mảng rỗng nếu lỗi
        } finally {
            // Dù thành công hay thất bại thì cũng tắt loading
            setIsLoading(false);
        }
    };

    // Tự động gọi API khi Component mount
    useEffect(() => {
        fetchAllData();
    }, []);

    // Trả về các state và hàm refetch để có thể tự gọi lại data nếu cần (nút refresh)
    return { allPosts, isLoading, error, refetch: fetchAllData };
};