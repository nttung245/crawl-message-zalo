"use client";

import React from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { RiDeleteBin6Line } from "react-icons/ri";
import { AiOutlineClose } from "react-icons/ai"; // Nút X từ react-icons

import { CreateBatchIntentsSchema, CreateBatchIntentsDTO, IntentItemDTO } from "../schemas/intent_schemas";
import { useCreateBatchIntents } from "../hooks/useCreateIntent";

// Khai báo giao tiếp rõ ràng với Component Cha
interface IntentBatchModalProps {
  isOpen: boolean;                                  // Trạng thái đóng/mở do cha kiểm soát
  onClose: () => void;                              // Hàm kích hoạt khi bấm Hủy hoặc nút X
  onSuccess: (createdIntents: IntentItemDTO[]) => void; // Callback trả về danh sách đã tạo cho cha
}

export function IntentBatchModal({ isOpen, onClose, onSuccess }: IntentBatchModalProps) {
  const { mutate: submitBatchIntents, isPending, errorMessage, clearMessages } = useCreateBatchIntents();

  // 1. Cấu hình Form
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateBatchIntentsDTO>({
    resolver: zodResolver(CreateBatchIntentsSchema),
    defaultValues: {
      intents: [{ name: "", value: "" }],
    },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "intents",
  });

  // Nếu modal không mở, không render HTML để tối ưu DOM
  if (!isOpen) return null;

  // 2. Xử lý Submit và trả kết quả về cho Cha
  const onSubmit = async (data: CreateBatchIntentsDTO) => {
    clearMessages();
    
    // Gọi hook xử lý API
    await submitBatchIntents(data, {
      onSuccess: () => {
        // Trả mảng dữ liệu về cho component cha xử lý tiếp (nếu cần)
        onSuccess(data.intents);
        
        // Reset form và đóng Modal
        reset({ intents: [{ name: "", value: "" }] });
        onClose();
      },
    });
  };

  // Hàm đóng an toàn (kèm reset dữ liệu đang nhập dở)
  const handleSafeClose = () => {
    clearMessages();
    reset({ intents: [{ name: "", value: "" }] });
    onClose();
  };

  return (
    /* LỚP NỀN MỜ (BACKDROP): Dùng fixed phủ kín màn hình và căn giữa Modal */
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 transition-all">
      
      {/* /* KHUNG MODAL CHÍNH: Giới hạn chiều cao max-h-[85vh] để không bị tràn màn hình */ }
      <div className="w-full max-w-3xl bg-white rounded-2xl shadow-2xl border border-slate-100 flex flex-col max-h-[85vh] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        {/* HEADER: Tiêu đề + Nút X */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/50">
          <div>
            <h2 className="text-xl font-bold text-slate-800">Thêm hàng loạt Intent</h2>
            <p className="text-xs text-slate-500 mt-0.5">Khai báo danh sách phân loại mới vào hệ thống</p>
          </div>
          
          {/* Nút X đóng Modal */}
          <button
            type="button"
            onClick={handleSafeClose}
            disabled={isPending}
            className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition"
          >
            <AiOutlineClose className="text-xl" />
          </button>
        </div>

        {/* BODY: Vùng nhập liệu (Cho phép cuộn nếu thêm quá nhiều dòng) */}
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col flex-1 overflow-hidden">
          
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            
            {/* Hiển thị lỗi API nếu có */}
            {errorMessage && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-600 rounded-xl text-sm font-medium">
                {errorMessage}
              </div>
            )}

            {/* Vòng lặp render các dòng */}
            {fields.map((field, index) => {
              const fieldErrors = errors.intents?.[index];

              return (
                <div
                  key={field.id}
                  className="grid grid-cols-1 md:grid-cols-12 gap-3 items-start p-3 bg-slate-50 border border-slate-200/60 rounded-xl relative"
                >
                  {/* Cột Name */}
                  <div className="md:col-span-5">
                    <input
                      type="text"
                      placeholder={`Intent Name ${index + 1} (vd: Tuyển dụng)`}
                      className={`w-full bg-white px-3 py-2 text-sm rounded-lg border outline-none transition ${
                        fieldErrors?.name ? "border-red-500 focus:ring-1 focus:ring-red-500" : "border-slate-200 focus:border-indigo-500"
                      }`}
                      {...register(`intents.${index}.name` as const)}
                    />
                    {fieldErrors?.name && (
                      <span className="text-xs text-red-500 mt-1 block">{fieldErrors.name.message}</span>
                    )}
                  </div>

                  {/* Cột Value */}
                  <div className="md:col-span-6">
                    <input
                      type="text"
                      placeholder={`Intent Value ${index + 1} (vd: recruitment)`}
                      className={`w-full bg-white px-3 py-2 text-sm rounded-lg border outline-none transition ${
                        fieldErrors?.value ? "border-red-500 focus:ring-1 focus:ring-red-500" : "border-slate-200 focus:border-indigo-500"
                      }`}
                      {...register(`intents.${index}.value` as const)}
                    />
                    {fieldErrors?.value && (
                      <span className="text-xs text-red-500 mt-1 block">{fieldErrors.value.message}</span>
                    )}
                  </div>

                  {/* Nút Xóa Dòng */}
                  <div className="md:col-span-1 flex justify-center pt-2">
                    {fields.length > 1 && (
                      <button
                        type="button"
                        onClick={() => remove(index)}
                        className="text-slate-400 hover:text-red-500 transition"
                      >
                        <RiDeleteBin6Line className="text-lg" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Nút Thêm Dòng */}
            <button
              type="button"
              onClick={() => append({ name: "", value: "" })}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1 mt-2"
            >
              + Thêm dòng mới
            </button>
          </div>

          {/* FOOTER: Nút Hủy và Xác Nhận */}
          <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex justify-end gap-3">
            <button
              type="button"
              onClick={handleSafeClose}
              disabled={isPending}
              className="px-5 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-200/60 rounded-xl border border-slate-200 transition"
            >
              Hủy
            </button>

            <button
              type="submit"
              disabled={isPending}
              className="px-6 py-2.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl transition disabled:opacity-50 shadow-md shadow-indigo-100"
            >
              {isPending ? "Đang xử lý..." : "Xác nhận tạo"}
            </button>
          </div>

        </form>

      </div>
    </div>
  );
}