"use client";

import React, { useEffect } from "react";
import { FaFacebook, FaLinkedin, FaLink, FaUsers, FaTags, FaInfoCircle, FaTimes } from "react-icons/fa";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { CreateGroupSchema, CreateGroupPayload, initialCreateGroupData } from "../schemas/create_groups_shemas";
import { useCreateGroup } from "../hooks/useCreateGroups";
import { useGetIntents } from "../hooks/useGetIntents";
import FullScreenLoading from "../../../shared/components/layout/FullScreenLoading"; 

// 1. Định nghĩa Props để nhận tín hiệu từ component cha
interface CreateGroupModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function CreateGroupModal({ isOpen, onClose }: CreateGroupModalProps) {
    // Hooks
    const { intents, fetchIntents } = useGetIntents();
    const { isLoading, submitGroupData } = useCreateGroup(); // Đã bỏ handleCancel vì giờ sẽ dùng onClose

    // Khởi tạo React Hook Form
    const {
        register,
        handleSubmit,
        watch,
        reset,
        formState: { errors }
    } = useForm({
        resolver: zodResolver(CreateGroupSchema),
        defaultValues: initialCreateGroupData
    });

    // Fetch dữ liệu Intents khi load trang
    useEffect(() => {
        if (isOpen) {
            fetchIntents();
        }
    }, [isOpen, fetchIntents]);

    // Xử lý logic submit
    const handleOnSubmit = async (data: CreateGroupPayload) => {
        const responseData = await submitGroupData(data);
        
        // Nếu API trả về dữ liệu thành công -> Reset form và đóng Modal
        if (responseData) {
            reset();
            onClose();
        }
    };

    // Hàm lấy lỗi đầu tiên
    const getFirstErrorMessage = (errorsObj: any): string | null => {
        if (!errorsObj) return null;
        if (errorsObj.message && typeof errorsObj.message === "string") {
            return errorsObj.message;
        }
        for (const key in errorsObj) {
            const found = getFirstErrorMessage(errorsObj[key]);
            if (found) return found;
        }
        return null;
    };

    const firstErrorMsg = getFirstErrorMessage(errors);
    const currentUrl = watch("link_group");
    const platform = currentUrl?.includes("linkedin.com") ? "LinkedIn" : "Facebook";

    // 2. Nếu cha truyền isOpen = false thì không render gì cả
    if (!isOpen) return null;

    return (
        <>
            {isLoading && (
                <FullScreenLoading
                    title="Tiến trình đang chạy"
                    content="Đang khởi tạo nhóm, vui lòng chờ..."
                    onCancel={onClose}
                />
            )}

            {/* 3. Lớp Overlay mờ (Fixed Background) */}
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 sm:p-6 overflow-y-auto">
                
                {/* 4. Container của Form */}
                <div className="relative w-full max-w-4xl mx-auto bg-white rounded-3xl shadow-2xl border border-slate-200 overflow-hidden font-sans my-auto">
                    
                    {/* Nút X góc trên cùng bên phải */}
                    <button 
                        onClick={onClose}
                        className="absolute top-6 right-6 text-slate-400 hover:text-rose-500 transition-colors z-10"
                    >
                        <FaTimes className="text-xl" />
                    </button>

                    {/* Header */}
                    <div className="w-full border-b bg-slate-50 px-8 py-6 pr-16">
                        <h1 className="text-2xl sm:text-3xl font-bold text-slate-800">Thêm Group Mới</h1>
                        <p className="text-sm text-slate-500 mt-1">Đăng ký các nhóm Facebook hoặc LinkedIn vào hệ thống</p>
                    </div>

                    <form onSubmit={handleSubmit(handleOnSubmit)}>
                        <div className="p-6 sm:p-8 space-y-8 max-h-[65vh] overflow-y-auto">
                            <div className="grid md:grid-cols-3 gap-6">
                                
                                {/* CỘT TRÁI: THÔNG TIN CHÍNH */}
                                <div className="md:col-span-2 space-y-6">
                                    <div className="space-y-4">
                                        
                                        {/* URL Group */}
                                        <div>
                                            <label className="block text-sm font-semibold mb-2 text-slate-900">
                                                Link URL Group <span className="text-rose-500">*</span>
                                            </label>
                                            <div className="relative">
                                                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
                                                    {currentUrl ? (
                                                        platform === "LinkedIn" ? <FaLinkedin className="text-blue-700 text-lg" /> : <FaFacebook className="text-blue-600 text-lg" />
                                                    ) : <FaLink className="text-lg" />}
                                                </div>
                                                <input
                                                    placeholder="https://www.facebook.com/groups/..."
                                                    className={`w-full pl-10 pr-4 py-3 bg-white border-2 rounded-xl text-sm outline-none transition-all duration-300
                                                        ${errors.link_group ? 'border-rose-500 text-rose-600' : 'border-slate-300 text-slate-900 focus:border-indigo-500'}`}
                                                    {...register("link_group")}
                                                />
                                            </div>
                                        </div>

                                        {/* Tên Group */}
                                        <div>
                                            <label className="block text-sm font-semibold mb-2 text-slate-900">
                                                Tên hiển thị Group <span className="text-rose-500">*</span>
                                            </label>
                                            <div className="relative">
                                                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
                                                    <FaUsers className="text-lg" />
                                                </div>
                                                <input
                                                    placeholder="Ví dụ: Cộng đồng Frontend Việt Nam"
                                                    className={`w-full pl-10 pr-4 py-3 bg-white border-2 rounded-xl text-sm outline-none transition-all duration-300
                                                        ${errors.group_name ? 'border-rose-500 text-rose-600' : 'border-slate-300 text-slate-900 focus:border-indigo-500'}`}
                                                    {...register("group_name")}
                                                />
                                            </div>
                                        </div>

                                        {/* Intent & Thành viên */}
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-sm font-semibold mb-2 text-slate-900">
                                                    Mục đích (Intent) <span className="text-rose-500">*</span>
                                                </label>
                                                <div className="relative">
                                                    <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
                                                        <FaTags className="text-lg" />
                                                    </div>
                                                    <select
                                                        className={`w-full pl-10 pr-4 py-3 bg-white border-2 rounded-xl text-sm outline-none transition-all duration-300 appearance-none cursor-pointer
                                                            ${errors.intent ? 'border-rose-500 text-rose-600' : 'border-slate-300 text-slate-900 focus:border-indigo-500'}`}
                                                        {...register("intent")}
                                                    >
                                                        <option value="" disabled>-- Chọn kịch bản --</option>
                                                        {intents?.map((item: any, index: number) => (
                                                            <option key={index} value={item.value}>{item.name}</option>
                                                        ))}
                                                    </select>
                                                </div>
                                            </div>

                                            <div>
                                                <label className="block text-sm font-semibold mb-2 text-slate-900">
                                                    Số lượng thành viên
                                                </label>
                                                <input
                                                    type="number"
                                                    placeholder="Vd: 5000"
                                                    className="w-full px-4 py-3 bg-white border-2 border-slate-300 text-slate-900 rounded-xl text-sm outline-none transition-all duration-300 focus:border-indigo-500"
                                                    {...register("members")}
                                                />
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* CỘT PHẢI: THIẾT LẬP PHỤ */}
                                <div className="space-y-6">
                                    <div className="bg-slate-50 p-6 rounded-2xl border border-slate-200">
                                        <h2 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
                                            <FaInfoCircle className="text-indigo-500 text-lg" /> Cấu hình bổ sung
                                        </h2>
                                        
                                        <div className="space-y-5">
                                            <div>
                                                <label className="block text-sm font-semibold mb-2 text-slate-900">
                                                    Ước tính Post/Tuần
                                                </label>
                                                <input
                                                    type="number"
                                                    className="w-full px-4 py-3 bg-white border-2 border-slate-300 text-slate-900 rounded-xl text-sm outline-none transition-all duration-300 focus:border-indigo-500"
                                                    {...register("posts_per_week")}
                                                />
                                            </div>

                                            <div className="flex items-center justify-between pt-2">
                                                <span className="text-sm font-semibold text-slate-900">Quét liên tục 24h</span>
                                                <label className="relative inline-flex items-center cursor-pointer">
                                                    <input 
                                                        type="checkbox" 
                                                        className="sr-only peer" 
                                                        {...register("chay_24h")}
                                                    />
                                                    <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600"></div>
                                                </label>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Footer / Nút Hành động */}
                        <div className="px-6 sm:px-8 py-5 bg-slate-50 border-t flex flex-col sm:flex-row justify-between items-center gap-4 sm:gap-0">
                            <p className={`text-sm transition-colors duration-300 max-w-lg ${firstErrorMsg ? 'text-red-500 font-medium' : 'text-slate-500'}`}>
                                {firstErrorMsg || "Vui lòng điền đầy đủ các thông tin bắt buộc (*) trước khi lưu."}
                            </p>
                            
                            <div className="flex gap-3 w-full sm:w-auto">
                                <button
                                    type="button"
                                    onClick={onClose}
                                    className="flex-1 sm:flex-none px-6 py-3 border border-slate-300 bg-white text-slate-700 rounded-xl font-semibold hover:bg-slate-100 transition"
                                >
                                    Hủy bỏ
                                </button>
                                <button
                                    type="submit"
                                    className="flex-1 sm:flex-none bg-violet-600 hover:bg-violet-700 text-white px-6 py-3 rounded-xl font-semibold transition shadow-md shadow-violet-200"
                                >
                                    Lưu Group
                                </button>
                            </div>
                        </div>
                    </form>
                </div>
            </div>
        </>
    );
}