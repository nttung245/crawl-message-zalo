import axiosClient from "../../../shared/api/axiosClient";
import { LoginFormValues } from "../schemas/login_shemas";

export interface AuthResponse {
  status: "success" | "need_otp" | "need_phone_approval" | "processing" | "error" | "error_bot_blocked";
  message?: string;
  session_id?: string;
}
export const AuthService = {
  // BƯỚC 1: Đăng nhập khởi tạo
  login: async (data: LoginFormValues): Promise<AuthResponse> => {
    const response = await axiosClient.post<AuthResponse>("/api/v1/auth/login", {
      email: data.email,
      password: data.password,
    });
    return response.data;
  },

  // BƯỚC 2: Gọi treo ngầm chờ phê duyệt điện thoại / hoặc chờ tự động nhảy sang OTP
  checkPhoneApproval: async (sessionId: string): Promise<AuthResponse> => {
    const response = await axiosClient.post<AuthResponse>("/api/v1/auth/check-phone-approval", {
      session_id: sessionId,
    });
    return response.data;
  },

  // BƯỚC 3: Gửi mã OTP vào phiên đang mở
  submitOtp: async (sessionId: string, otpCode: string): Promise<AuthResponse> => {
    const response = await axiosClient.post<AuthResponse>("/api/v1/auth/submit-otp", {
      session_id: sessionId,
      otp_code: otpCode,
    });
    return response.data;
  },
};
