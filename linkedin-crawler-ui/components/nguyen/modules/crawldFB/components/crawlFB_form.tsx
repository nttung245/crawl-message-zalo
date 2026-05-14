"use client"
import { useState } from "react";
import { RiDeleteBin6Line } from "react-icons/ri";
import FacebookPosts from "./processRawFacebookPosts";
import { FaEye, FaEyeSlash } from "react-icons/fa";
import { CrawlFb_Schemas, CrawlFb_form } from "../schemas/crawlFb_schemas";
import { useForm, useFieldArray } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod";
import { useAuthContext } from "../../../shared/components/contexts/AuthContext";
import FullScreenLoading from "../../../shared/components/layout/FullScreenLoading";
import { useCrawlFB } from "../hooks/useCrawlFB";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { CrawlIntentOption } from "../types/dataFb.type";
import { IntentBatchModal } from "./intent_component";
import { IntentItemDTO } from "../schemas/intent_schemas";
import { useGetIntents } from "../hooks/useGetIntents";

// Mảng dữ liệu tĩnh (Nên viết hoa tên biến để thể hiện đây là Constant)
import { SelectPresetGroupsModal } from "./SelectPresetGroupsModal";
export default function CrawlFB_Form() {
    const route = useRouter()
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isPresetModalOpen, setIsPresetModalOpen] = useState(false);
    const { intents, isLoading: isLoadingIntents, fetchIntents } = useGetIntents();
    const [localIntentsList, setLocalIntentsList] = useState<IntentItemDTO[]>([]); // State nội bộ để quản lý danh sách intent hiển thị trong form
    // 2. Tải dữ liệu ngay khi Component được vẽ ra
    useEffect(() => {
        const loadApiData = async () => {
            const fetchedData = await fetchIntents();
            if (fetchedData && fetchedData.length > 0) {
                // Nối dữ liệu API mới tải đằng sau các kịch bản chuẩn gốc
                setLocalIntentsList(fetchedData);
            }
        };
        loadApiData();
    }, [fetchIntents]);

    // hàm sử lý dữ liệu sau khi tạo intent thành công, nhận dữ liệu từ component con (IntentBatchModal)
    const handleCreatedSuccess = (newIntents: IntentItemDTO[]) => {
        console.log("Danh sách Intent vừa tạo thành công:", newIntents);

        // Cập nhật state nội bộ ở cha hoặc làm các Side-effect khác
        setLocalIntentsList((prev) => [...newIntents, ...prev]);
    };


    const { user, isLoading: isLoadingLogin } = useAuthContext();

    const {
        register,
        handleSubmit,
        control,
        watch,
        setValue,
        formState: { errors }
    } = useForm({
        resolver: zodResolver(CrawlFb_Schemas),
        defaultValues: {
            isDefaultAccount: false,
            userName: user?.email || "",
            password: "",

            rows: [{ name: "", url: "", Intent: "" }],
        }
    })
    const { fields, append, remove } = useFieldArray({
        control,
        name: "rows",
    });
    // useEffect(() => {
    //     // Chỉ chạy logic khi đã loading xong thông tin user
    //     if (!isLoadingLogin) {
    //         if (user?.email) {
    //             // Nếu có email -> Điền tự động vào form
    //             setValue("userName", user.email);
    //         } else {
    //             // Nếu không có email -> Đẩy về trang chủ một cách an toàn
    //             route.push("/");
    //         }
    //     }
    // }, [isLoadingLogin, user?.email, setValue, route]);

    const [isEye, setIsEye] = useState<boolean>(false)

    const { isLoading, loadingMsg, submitCrawlData, result, cancelCrawl } = useCrawlFB();

    const HandleOnsubmit = async (data: CrawlFb_form) => {
        submitCrawlData(data);
    };



    // Hàm tìm lỗi đầu tiên từ object errors của React Hook Form
    const getFirstErrorMessage = (errorsObj: any): string | null => {
        if (!errorsObj) return null;

        // Nếu tìm thấy trường có chứa message là chuỗi, trả về luôn
        if (errorsObj.message && typeof errorsObj.message === "string") {
            return errorsObj.message;
        }

        // Nếu là object hoặc mảng (như mảng rows), lặp qua các phần tử bên trong
        for (const key in errorsObj) {
            const found = getFirstErrorMessage(errorsObj[key]);
            if (found) return found;
        }

        return null;
    };
    const firstErrorMsg = getFirstErrorMessage(errors);

    const handleSelectPresetGroups = (selectedGroups: { name: string; url: string; intent: string }[]) => {


        // Lặp qua mảng kết quả và chèn tự động các dòng mới vào Form
        selectedGroups.forEach((group) => {
            append({
                name: group.name,
                url: group.url,
                Intent: group.intent, // Đổ thẳng kịch bản đã tick chọn từ Modal vào Dropdown của dòng
            });
        });
    };
    return (
        <>
            {isLoading && (
                <FullScreenLoading
                    title="Tiến trình đang chạy"
                    content={loadingMsg}
                    onCancel={cancelCrawl}
                />
            )
            }

            <div className="w-full max-w-4xl bg-white rounded-3xl shadow-xl border border-slate-200 overflow-hidden">
                <div className="w-full flex justify-between items-center border-b bg-slate-50 px-8 py-6 ">
                    <div className="">
                        <h1 className="text-3xl font-bold text-slate-800">Crawl dữ liệu từ facebook</h1>
                        <p className="text-sm text-slate-500 mt-1">Quản lý và xử lý dữ liệu nguồn tự động</p>
                    </div>
                    <button
                        type="button"
                        onClick={() => setIsModalOpen(true)}
                        className="border border-violet-300 text-green-600 px-5 py-3 rounded-xl font-semibold hover:bg-green-200 transition"
                    >
                        + Thêm intent mới
                    </button>
                </div>
                <form action="" onSubmit={handleSubmit(HandleOnsubmit)}>
                    <div className="p-8 space-y-8">
                        <div className="grid md:grid-cols-2 gap-6 items-end">
                            <div>
                                <label
                                    htmlFor="useName"
                                    className={`block text-sm font-semibold mb-2 transition-colors duration-300 \
                                ${watch("isDefaultAccount") ? 'text-slate-400' : 'text-slate-900'}`}>
                                    Email đăng nhập
                                </label>
                                <input
                                    id="useName"
                                    disabled={true}
                                    placeholder="email or phone"
                                    className={`w-full border-2 border-dashed rounded-xl px-4 py-3 outline-none transition-all duration-300
                                     ${watch("isDefaultAccount")
                                            ? 'bg-slate-200 text-slate-400 border-slate-300 cursor-not-allowed'
                                            : 'bg-white text-slate-900 border-slate-300 '
                                        }`}
                                    {...register("userName")}
                                />
                            </div>
                            <div className="mb-2">
                            <a href="/minhhoang-scraper/loginFb"
                                className="border border-violet-300 text-violet-600 px-5 py-3 rounded-xl font-semibold hover:bg-violet-50 transition"
                            >
                                Xác nhận tài khoản FB
                            </a>
                            </div>
                        </div>

                        <div className="flex items-center gap-3">
                            <input
                                type="checkbox"
                                className="w-5 h-5 cursor-pointer"
                                checked={watch("isDefaultAccount")}
                                {...register("isDefaultAccount")}
                            />
                            <span className="text-sm text-slate-700">Sử dụng tài khoản mặc định</span>
                        </div>

                        <div className="space-y-4">
                            {fields.map((field, index) => (
                                <div key={index} className="grid md:grid-cols-12 gap-4 items-center">
                                    <input
                                        placeholder="Nhập tên dữ liệu"
                                        className="md:col-span-3 border text-black rounded-xl px-4 py-3"
                                        {...register(`rows.${index}.name` as const)}
                                    />
                                    <input
                                        placeholder="https://"
                                        className="md:col-span-5 border text-black rounded-xl px-4 py-3"
                                        {...register(`rows.${index}.url` as const)}
                                    />
                                    <select
                                        id="intentSelect"
                                        className={`md:col-span-3 w-full border-2 rounded-xl px-4 py-3 outline-none transition-all bg-white text-slate-900  border-slate-300
                                            `}
                                        {...register(`rows.${index}.Intent` as const)}
                                    >
                                        {/* Option mặc định dùng để hướng dẫn user */}
                                        <option value="" disabled>-- Chọn kịch bản quét --</option>

                                        {/* Render tự động từ mảng */}
                                        {localIntentsList.map((item, index) => (
                                            <option key={index} value={item.value}>
                                                {item.name}
                                            </option>
                                        ))}
                                    </select>
                                    <button
                                        type="button"
                                        onClick={() => remove(index)}
                                        className="md:col-span-1 text-red-500 font-bold hover:scale-110 transition"
                                    >
                                        < RiDeleteBin6Line className="text-xl" />
                                    </button>
                                </div>
                            ))}
                        </div>
                        <div className="flex w-full justify-between">
                            <button

                                type="button"
                                onClick={() => { append({ name: "", url: "", Intent: "" }) }}
                                className="border border-violet-300 text-violet-600 px-5 py-3 rounded-xl font-semibold hover:bg-violet-50 transition"
                            >
                                + Thêm dòng mới
                            </button>
                            <button

                                type="button"
                                onClick={() => setIsPresetModalOpen(true)}
                                className="border border-violet-300 text-violet-600 px-5 py-3 rounded-xl font-semibold hover:bg-violet-50 transition"
                            >
                                Chọn groups có sẵn
                            </button>
                        </div>
                    </div>

                    <div className="px-8 py-5 bg-slate-50 border-t flex justify-between items-center">
                        <p className={`text-sm mt-4 transition-colors duration-300 ${firstErrorMsg ? 'text-red-500 font-medium' : 'text-slate-500'}`}>
                            {firstErrorMsg || "Vui lòng điền đầy đủ thông tin trước khi xử lý."}
                        </p>
                        <button
                            type="submit"
                            className="bg-violet-600 hover:bg-violet-700 text-white px-6 py-3 rounded-xl font-semibold transition">
                            Xử lý dữ liệu
                        </button>
                    </div>
                </form>
            </div>


            {/* kết quả hiển thị ở đây */}
            {result &&
                <FacebookPosts mockPosts={result} />
            }


            <IntentBatchModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onSuccess={handleCreatedSuccess} // Gửi Callback xuống cho con
            />
            <SelectPresetGroupsModal
                isOpen={isPresetModalOpen}
                onClose={() => setIsPresetModalOpen(false)}
                onSelectGroups={handleSelectPresetGroups} // Gửi Callback xuống cho con
            />

        </>

    );
}
