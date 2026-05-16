import { useState } from "react";
import { AuthService } from "../services/login";
import { useAuthContext } from "../../../shared/components/contexts/AuthContext";
import { LoginFormValues } from "../schemas/login_shemas";
import { useRouter } from "next/navigation";

export const useAuthHook = () => {
  const route = useRouter();
  const { saveUserSession } = useAuthContext();
  
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  const [isOtpModalOpen, setIsOtpModalOpen] = useState<boolean>(false);
  const [currentSessionId, setCurrentSessionId] = useState<string>("");

  const handleLogin = async (values: LoginFormValues) => {
    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      // Gọi API login bước 1
      const res = await AuthService.login(values);

      if (res.status === "success") {
        setIsLoading(false);
        setSuccessMessage("Đăng nhập thành công!");
        saveUserSession(values.userName, values.password);
        route.push("/minhhoang-scraper");
      } 
      else if (res.status === "need_otp" && res.session_id) {
        setIsLoading(false);
        setCurrentSessionId(res.session_id);
        setIsOtpModalOpen(true);
      } 
      // SỬA LỖI 2: Gộp chung xử lý "need_phone_approval" VÀ "processing" (mạng chậm)
      // Cả 2 trường hợp này đều tiếp tục gọi API bước 2 để chờ kết quả chính xác
      else if ((res.status === "need_phone_approval" || res.status === "processing") && res.session_id) {
        const sessionId = res.session_id;
        setCurrentSessionId(sessionId);
        
        // Hiển thị lời nhắc chính xác theo trạng thái
        if (res.status === "need_phone_approval") {
          setSuccessMessage("Vui lòng MỞ ĐIỆN THOẠI bấm xác nhận 'Đây là tôi'. Đang chờ đồng bộ (tối đa 60s)...");
        } else {
          setSuccessMessage("Hệ thống đang xử lý đăng nhập ngầm, vui lòng giữ nguyên trang...");
        }
        
        // Gọi API bước 2 để tiếp tục lắng nghe tiến trình ngầm
        try {
          const approvalRes = await AuthService.checkPhoneApproval(sessionId);
          
          if (approvalRes.status === "success") {
            setIsLoading(false);
            setSuccessMessage("Đăng nhập thành công!");
            saveUserSession(values.userName, values.password);
            route.push("/minhhoang-scraper");
          } 
          else if (approvalRes.status === "need_otp") {
            setIsLoading(false);
            setSuccessMessage(null); 
            setIsOtpModalOpen(true); 
          } 
          // Bắt chính xác lỗi out ra cho FE
          else if (approvalRes.status === "error_bot_blocked") {
            setIsLoading(false);
            setSuccessMessage(null);
            setErrorMessage("Đăng nhập thất bại: Tài khoản bị Facebook chặn xác minh Bot/CAPTCHA.");
          }
          else {
            setIsLoading(false);
            setSuccessMessage(null);
            // Sẽ hiển thị chuẩn thông báo "Sai email hoặc mật khẩu" từ Backend truyền về
            setErrorMessage(approvalRes.message || "Đăng nhập thất bại.");
          }
        } catch (err) {
          setIsLoading(false);
          setErrorMessage("Mất kết nối với máy chủ khi đang theo dõi đăng nhập.");
        }
      } 
      else if (res.status === "error_bot_blocked") {
        setIsLoading(false);
        setErrorMessage("Đăng nhập thất bại: Tài khoản bị Facebook chặn xác minh Bot/CAPTCHA.");
      } 
      // Trạng thái error (Sai pass ngay từ đầu)
      else {
        setIsLoading(false);
        setErrorMessage(res.message || "Đăng nhập thất bại. Vui lòng kiểm tra lại thông tin.");
      }
    } catch (error) {
      setIsLoading(false);
      setErrorMessage("Lỗi kết nối đến máy chủ.");
    }
  };
  const handleVerifyOtp = async (otpCode: string, originalValues: LoginFormValues) => {
    if (!otpCode.trim()) {
      setErrorMessage("Vui lòng nhập mã OTP");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      // Gửi mã OTP kèm session_id để điền tiếp vào trình duyệt đang mở ngầm
      const res = await AuthService.submitOtp(currentSessionId, otpCode);

      if (res.status === "success") {
        setIsLoading(false);
        setSuccessMessage("Xác thực OTP thành công!");
        setIsOtpModalOpen(false);
        
        saveUserSession(originalValues.userName, originalValues.password);
        route.push("/minhhoang-scraper");
      } else {
        setIsLoading(false);
        setErrorMessage(res.message || "Mã OTP không chính xác hoặc đã hết hạn.");
      }
    } catch (error) {
      setIsLoading(false);
      setErrorMessage("Lỗi xác thực OTP với máy chủ.");
    }
  };

  return {
    isLoading,
    errorMessage,
    successMessage,
    isOtpModalOpen,
    setIsOtpModalOpen,
    handleLogin,
    handleVerifyOtp,
  };
};