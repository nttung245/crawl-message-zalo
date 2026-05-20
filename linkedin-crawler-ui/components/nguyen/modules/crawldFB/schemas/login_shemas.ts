import { z } from "zod";
// Giả sử import custom validator của bạn vào (hoặc tự viết trực tiếp bằng Zod)
// import { validator } from "@/src/shared/lib/validations";

export const Login_Schemas = z.object({
    // 1. Nếu bạn thực sự muốn nó OPTIONAL (Không bắt buộc nhập lúc đầu):
    // userName: z.string().optional(),
    // password: z.string().optional(),

    // 2. [ĐỀ XUẤT] - Đã làm Form Login thì BẮT BUỘC phải nhập và phải chuẩn:
    email: z.string({ error: "Vui lòng nhập tài khoản" })
        .trim() // Tự động cắt khoảng trắng thừa ở đầu/cuối
        .min(1, "Tài khoản không được để trống"),
    secret_2fa:z.string().optional(),
    password: z.string({ error: "Vui lòng nhập mật khẩu" })
        .min(6, "Mật khẩu phải có ít nhất 6 ký tự"), 
        // Tip: Login thì không nên dùng regex check mật khẩu quá khắt khe như lúc Register, 
        // cứ để user nhập, sai thì backend báo.
});

// SỬA LẠI TÊN CHUẨN XÁC: Infer đúng từ Login_Schemas
export type LoginFormValues = z.infer<typeof Login_Schemas>;