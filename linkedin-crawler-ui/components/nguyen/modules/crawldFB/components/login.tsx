"use client";
import { FaEye, FaEyeSlash } from "react-icons/fa";
import { Login_Schemas, LoginFormValues } from "../schemas/login_shemas";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useAuthHook } from "../hooks/useLogin";

export default function LoginPage() {
  const [isEye, setIsEye] = useState<boolean>(false);
  const [otpInput, setOtpInput] = useState<string>("");

  // Nạp Custom Hook xử lý API
  const {
    isLoading,
    errorMessage,
    successMessage,
    isOtpModalOpen,
    setIsOtpModalOpen,
    handleLogin,
    handleVerifyOtp,
  } = useAuthHook();

  const { register, handleSubmit, getValues, formState: { errors } } = useForm<LoginFormValues>({
    resolver: zodResolver(Login_Schemas),
    defaultValues: { email: "", password: "", secret_2fa: "" },
  });

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-100 p-6 relative">
      <div className="w-130 bg-white rounded-3xl shadow-xl border border-slate-200 p-8">
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-40 h-16 rounded-2xl bg-indigo-600 flex items-center justify-center shadow-lg text-white text-3xl font-bold">
            CrawlFB
          </div>
          <p className="text-slate-500 text-sm mt-2">Hệ thống tự động hóa thu thập dữ liệu</p>
        </div>

        {/* Hiển thị thông báo chung */}
        {errorMessage && <div className="mb-4 p-3 bg-red-50 text-red-600 text-sm rounded-xl border border-red-200">{errorMessage}</div>}
        {successMessage && <div className="mb-4 p-3 bg-green-50 text-green-600 text-sm rounded-xl border border-green-200">{successMessage}</div>}

        <form onSubmit={handleSubmit(handleLogin)} className="space-y-5">
          <div>
            <label htmlFor="userName" className="block text-sm font-semibold mb-2 text-slate-900">Email đăng nhập</label>
            <input
              id="userName"
              placeholder="email or phone"
              className="w-full border-2 border-dashed rounded-xl px-4 py-3 outline-none transition-all duration-300 bg-white text-slate-900 border-slate-300 focus:border-indigo-600"
              {...register("email")}
            />
            {errors.email && <span className="text-xs text-red-500 mt-1 block">{errors.email.message}</span>}
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-semibold text-slate-700 mb-2">Mật khẩu</label>
            <div className="w-full relative flex items-center">
              <input
                id="password"
                type={isEye ? "text" : "password"}
                placeholder={isEye ? "Nhập mật khẩu" : "••••••••"}
                className="w-full border-2 border-dashed rounded-xl px-4 py-3 outline-none transition-all duration-300 bg-white text-slate-900 border-slate-300 focus:border-indigo-600"
                {...register("password")}
              />
              <button type="button" className="absolute right-3 text-gray-500 hover:text-indigo-600" onClick={() => setIsEye(!isEye)}>
                {isEye ? <FaEye className="text-xl" /> : <FaEyeSlash className="text-xl" />}
              </button>
            </div>
            {errors.password && <span className="text-xs text-red-500 mt-1 block">{errors.password.message}</span>}
          </div>

          <div>
            <label htmlFor="secret_2fa" className="block text-xs font-semibold text-slate-500 mb-1">Mã Secret 2FA (Tùy chọn - Tự động giải)</label>
            <input
              id="secret_2fa"
              placeholder="JBSWY3DPEHPK3PXP..."
              className="w-full border rounded-lg px-3 py-2 text-sm outline-none bg-slate-50 border-slate-200"
              {...register("secret_2fa")}
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className={`w-full bg-indigo-700 hover:bg-indigo-800 transition text-white font-semibold py-3 rounded-xl shadow-md ${isLoading ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            {isLoading ? "Đang xử lý..." : "Đăng nhập"}
          </button>
        </form>
      </div>

      {/* MODAL / POPUP NHẬP MÃ OTP */}
      {isOtpModalOpen && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
          <div className="bg-white w-full max-w-sm rounded-3xl p-6 shadow-2xl border border-slate-100 flex flex-col items-center">
            <div className="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center text-amber-600 mb-4 text-xl font-bold">!</div>
            <h3 className="text-lg font-bold text-slate-900 mb-1">Yêu cầu xác thực OTP</h3>
            <p className="text-xs text-slate-500 text-center mb-4">Facebook đang yêu cầu nhập mã gửi về điện thoại/email của bạn.</p>
            
            <input
              type="text"
              maxLength={8}
              placeholder="Nhập mã 6-8 số"
              value={otpInput}
              onChange={(e) => setOtpInput(e.target.value)}
              className="w-full border-2 border-indigo-200 rounded-xl px-4 py-3 text-center text-lg font-bold tracking-widest outline-none focus:border-indigo-600 mb-4"
            />

            <div className="flex w-full space-x-3">
              <button
                type="button"
                onClick={() => setIsOtpModalOpen(false)}
                className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold py-2 rounded-xl text-sm transition"
              >
                Hủy
              </button>
              <button
                type="button"
                disabled={isLoading}
                onClick={() => handleVerifyOtp(otpInput, getValues())}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2 rounded-xl text-sm shadow transition"
              >
                {isLoading ? "Đang gửi..." : "Xác nhận"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}