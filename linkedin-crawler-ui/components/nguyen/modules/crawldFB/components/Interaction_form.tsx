"use client";
import React, { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { FaUser, FaPaperPlane } from "react-icons/fa";
import { InteractionSchema, InteractionPayload } from "../schemas/Interaction_schemas";
import { useInteractPost } from "../hooks/useInteractPost";
import { useAuthContext } from "@/components/nguyen/shared/components/contexts/AuthContext";
interface InteractionFormProps {
    url: string;
}


import { useGetInteractions } from "../hooks/useGetInteraction";
// Dùng trực tiếp Emoji vào chuỗi label
const REACTIONS = [
    { value: "LIKE", label: "👍 Thích" },
    { value: "LOVE", label: "❤️ Yêu thích" },
    { value: "CARE", label: "🫂 Thương thương" },
    { value: "HAHA", label: "😂 Haha" },
    { value: "WOW", label: "😲 Wow" },
    { value: "SAD", label: "😢 Buồn" },
    { value: "ANGRY", label: "😡 Phẫn nộ" },
];

export function InteractionForm({ url }: InteractionFormProps) {
    const { user } = useAuthContext();
     const { interactions, error, fetchInteractions } = useGetInteractions();
    
        useEffect(() => {
            fetchInteractions();
        }, [fetchInteractions]);
    
    const { isLoading, submitInteraction } = useInteractPost();

    const {
        register,
        handleSubmit,
        setValue,
        formState: { errors },
        reset
    } = useForm<InteractionPayload>({
        resolver: zodResolver(InteractionSchema),
        defaultValues: {
            url: url,
            id: "",
            reaction: "LIKE",
            comment: "",
            name: "",
            email: user?.email || "",
            password: user?.password || "",
        },
    });

    const onSubmit = async (data: InteractionPayload) => {
        const result = await submitInteraction(data);
        if (result) {
            reset({ ...data, comment: "" });
        }
    };

    return (
        <form onSubmit={handleSubmit(onSubmit)} className="mt-4 rounded-xl bg-gray-50 p-3 border border-gray-100 flex flex-col gap-3">
            <div className="flex flex-col sm:flex-row gap-3">
                
                {/* Chọn User */}
                <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-2 w-full sm:w-1/3 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 transition-all">
                    <FaUser className="text-gray-400 shrink-0" />
                    <select
                        {...register("id")}
                        className="w-full bg-transparent outline-none text-sm text-gray-700 cursor-pointer"
                    onChange={(e) => {setValue("name", e.target.options[e.target.selectedIndex].text);}}
                    >
                        <option value="">-- Chọn User --</option>
                        {interactions.map((u) => (
                            <option key={u.id} value={u.id}>{u.name}</option>
                        ))}
                    </select>
                </div>

                {/* Chọn Cảm xúc: Cực kỳ gọn gàng với Emoji trong thẻ thuần */}
                <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-2 w-full sm:w-1/4 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 transition-all">
                    <select
                        {...register("reaction")}
                        className="w-full bg-transparent outline-none text-sm text-gray-700 cursor-pointer"
                    >
                        {REACTIONS.map((r) => (
                            <option key={r.value} value={r.value}>
                                {r.label}
                            </option>
                        ))}
                    </select>
                </div>

                {/* Nhập Bình luận & Nút Gửi */}
                <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-1.5 w-full sm:flex-1 focus-within:border-indigo-500 focus-within:ring-1 focus-within:ring-indigo-500 transition-all">
                    <input
                        {...register("comment")}
                        type="text"
                        placeholder="Viết bình luận..."
                        className="w-full bg-transparent outline-none text-sm text-gray-700 py-1"
                        autoComplete="off"
                    />
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white p-2 rounded-lg transition-colors shrink-0 flex items-center justify-center"
                        title="Gửi tương tác"
                    >
                        <FaPaperPlane className="text-sm" />
                    </button>
                </div>
            </div>

            {/* Hiển thị lỗi validation */}
            {errors.id && <span className="text-xs text-red-500 ml-1 font-medium">* {errors.id.message}</span>}
        </form>
    );
}