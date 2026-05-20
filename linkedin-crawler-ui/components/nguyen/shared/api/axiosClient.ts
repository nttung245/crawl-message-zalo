import axios from "axios";

const axiosClient = axios.create({
    // Thay bằng URL API thật của bạn (có thể dùng biến môi trường .env)
    baseURL: `${process.env.NEXT_PUBLIC_API_FACEBOOK_BASE_URL}/facebook`,
    headers: {
        "Content-Type": "application/json",
    },
});
export default axiosClient;