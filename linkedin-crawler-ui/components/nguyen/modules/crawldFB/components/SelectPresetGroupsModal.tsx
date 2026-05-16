// src/modules/group/components/SelectPresetGroupsModal.tsx
"use client";

import React, { useState, useEffect } from "react";
import { AiOutlineClose } from "react-icons/ai";
import { FaFacebook } from "react-icons/fa";
import { FacebookGroupDTO } from "../types/dataFb.type";
import { useGetIntents } from "../hooks/useGetIntents";
import { useGetPresetGroups } from "../hooks/useGetPresetGroups";

interface SelectPresetGroupsModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSelectGroups: (selectedGroups: { name: string; url: string; intent: string }[]) => void;
}
type GroupStatus = "ACTIVE" | "IDLE" | "DEAD" | null | undefined;
export function SelectPresetGroupsModal({ isOpen, onClose, onSelectGroups }: SelectPresetGroupsModalProps) {
    const [selectedIndices, setSelectedIndices] = useState<number[]>([]);
    const [searchTerm, setSearchTerm] = useState<string>("");

    const { intents, fetchIntents } = useGetIntents();
    const { presetGroups, isLoadingGroups, errorGroups, fetchPresetGroups } = useGetPresetGroups();

    useEffect(() => {
        if (isOpen) {
            fetchIntents();
            fetchPresetGroups();
            setSelectedIndices([]); 
        }
    }, [isOpen, fetchIntents, fetchPresetGroups]);

    if (!isOpen) return null;

    // Quản lý Tick chọn
    const handleToggleSelect = (targetIndex: number) => {
        setSelectedIndices((prev) => {
            const isExist = prev.includes(targetIndex);
            if (isExist) return prev.filter((i) => i !== targetIndex);
            return [...prev, targetIndex];
        });
    };

    const handleToggleSelectAll = () => {
        if (selectedIndices.length === presetGroups.length) {
            setSelectedIndices([]);
        } else {
            setSelectedIndices(presetGroups.map((_, index) => index));
        }
    };

    // Xác nhận trả về Form cha
    const handleConfirmSelection = () => {
        const payload = selectedIndices.map((targetIndex) => {
            const originalGroup = presetGroups[targetIndex];
            const matchedIntent = intents.find((item) => item.name === originalGroup.intent);

            return {
                name: originalGroup.group_name, 
                url: originalGroup.url,
                intent: matchedIntent ? matchedIntent.value : originalGroup.intent,
            };
        });

        onSelectGroups(payload);
        setSelectedIndices([]);
        onClose();
    };

    // Helpers UI
    const renderHealthScore = (score: number, status: GroupStatus) => {
        let bgColor = "bg-rose-500";
        let textColor = "text-rose-600";

        if (status === "ACTIVE") {
            bgColor = "bg-emerald-500";
            textColor = "text-emerald-600";
        } else if (status === "IDLE") {
            bgColor = "bg-amber-500";
            textColor = "text-amber-600";
        }

        // Đảm bảo % width không vượt quá 100% nếu điểm API trả về bị lố
        const progressWidth = Math.min(Math.max(score, 0), 100);

        return (
            <div className="flex items-center gap-2">
                <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div 
                        className={`h-full ${bgColor} transition-all duration-300`} 
                        style={{ width: `${progressWidth}%` }} 
                    />
                </div>
                <span className={`text-xs font-bold ${textColor}`}>
                    {score}
                </span>
            </div>
        );
    };

    const renderStatusBadge = (status?: "ACTIVE" | "IDLE" | "DEAD" | null) => {
    // Luôn có trường hợp fallback mặc định nếu API văng lỗi thiếu trường
    if (!status) return <span className="text-slate-400 italic text-xs">Chưa rõ</span>;

    switch (status) {
        case "ACTIVE":
            // < 24h: Màu xanh lá + Hiệu ứng chấm tròn nhấp nháy (Sống)
            return (
                <span className="px-2.5 py-1 bg-emerald-50 text-emerald-600 border border-emerald-100 rounded-full text-xs font-medium flex items-center gap-1 w-max">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> 
                    Sống
                </span>
            );
        case "IDLE":
            // <= 3 ngày: Màu vàng cam (Ít hoạt động)
            return (
                <span className="px-2.5 py-1 bg-amber-50 text-amber-600 border border-amber-100 rounded-full text-xs font-medium flex items-center gap-1 w-max">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500" /> 
                    Ít HĐ
                </span>
            );
        case "DEAD":
            // > 3 ngày: Màu đỏ (Chết)
            return (
                <span className="px-2.5 py-1 bg-rose-50 text-rose-600 border border-rose-100 rounded-full text-xs font-medium flex items-center gap-1 w-max">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500" /> 
                    Chết
                </span>
            );
    }
};

    // ✅ Helper format ngày tháng: Giúp chuỗi ngày in ra gọn đẹp, tránh TH chuỗi ISO quá dài
    const formatCrawlDate = (dateStr?: string | null) => {
        if (!dateStr) return <span className="text-slate-400 italic">Chưa crawl</span>;
        // Nếu Backend đã trả về chuỗi đẹp sẵn (vd: "2g trước" hoặc "12/05/2026") thì hiển thị luôn
        return <span className="text-slate-600 font-medium">{dateStr}</span>;
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
            <div className="w-full max-w-6xl bg-white rounded-2xl shadow-2xl border border-slate-100 flex flex-col max-h-[85vh] overflow-hidden animate-in fade-in duration-200">

                {/* HEADER */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/50">
                    <div>
                        <h2 className="text-xl font-bold text-slate-800">Chọn Facebook Groups có sẵn</h2>
                        <p className="text-xs text-slate-500 mt-0.5">Hệ thống tự động đồng bộ các group đã được theo dõi</p>
                    </div>
                    <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-full transition">
                        <AiOutlineClose className="text-xl" />
                    </button>
                </div>

                {/* TOOLBAR TÌM KIẾM */}
                <div className="p-4 border-b border-slate-100 bg-white">
                    <input
                        type="text"
                        disabled={isLoadingGroups}
                        placeholder="🔍 Tìm kiếm theo tên hoặc URL group..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full max-w-md bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 text-sm outline-none focus:border-violet-500 transition disabled:bg-slate-100"
                    />
                </div>

                {/* BẢNG DỮ LIỆU CHÍNH */}
                <div className="flex-1 overflow-auto relative">
                    
                    {errorGroups && (
                        <div className="m-4 p-3 bg-red-50 border border-red-200 text-red-600 rounded-xl text-sm font-medium">
                            {errorGroups}
                        </div>
                    )}

                    <table className="w-full border-collapse text-left">
                        <thead className="bg-slate-50 border-b border-slate-100 text-[11px] font-bold text-slate-400 uppercase tracking-wider sticky top-0 z-10">
                            <tr>
                                <th className="py-3 px-4 w-12">
                                    <input
                                        type="checkbox"
                                        disabled={isLoadingGroups || presetGroups.length === 0}
                                        checked={presetGroups.length > 0 && selectedIndices.length === presetGroups.length}
                                        onChange={handleToggleSelectAll}
                                        className="w-4 h-4 rounded border-slate-300 accent-violet-600 cursor-pointer"
                                    />
                                </th>
                                <th className="py-3 px-4">Tên Group</th>
                                <th className="py-3 px-4">Intent</th>
                                <th className="py-3 px-4">Thành viên</th>
                                <th className="py-3 px-4">Health Score</th>
                                <th className="py-3 px-4">Trạng thái</th>
                                
                                {/* ✅ BỔ SUNG TIÊU ĐỀ CỘT CRAWL GẦN NHẤT */}
                                <th className="py-3 px-4">Crawl gần nhất</th>
                                
                                <th className="py-3 px-4 text-center">Chạy 24h</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 text-xs text-slate-600">
                            
                            {isLoadingGroups ? (
                                <tr>
                                    <td colSpan={8} className="py-12 text-center text-slate-400 font-medium">
                                        <div className="flex flex-col items-center justify-center gap-2">
                                            <div className="w-6 h-6 border-2 border-violet-600 border-t-transparent rounded-full animate-spin" />
                                            <span>Đang kết nối tải dữ liệu từ hệ thống...</span>
                                        </div>
                                    </td>
                                </tr>
                            ) : (
                                presetGroups.map((group, index) => {
                                    const isMatchSearch = (group.group_name || "").toLowerCase().includes(searchTerm.toLowerCase()) || 
                                                          (group.url || "").toLowerCase().includes(searchTerm.toLowerCase());
                                    if (!isMatchSearch) return null;

                                    const isSelected = selectedIndices.includes(index);

                                    return (
                                        <tr
                                            key={index}
                                            onClick={() => handleToggleSelect(index)}
                                            className={`hover:bg-slate-50/80 cursor-pointer transition ${isSelected ? 'bg-violet-50/50' : ''}`}
                                        >
                                            <td className="py-3.5 px-4" onClick={(e) => e.stopPropagation()}>
                                                <input
                                                    type="checkbox"
                                                    checked={isSelected}
                                                    onChange={() => handleToggleSelect(index)}
                                                    className="w-4 h-4 rounded border-slate-300 accent-violet-600 cursor-pointer"
                                                />
                                            </td>

                                            <td className="py-3.5 px-4">
                                                <div className="font-bold text-slate-900 text-sm flex items-center gap-1.5">
                                                    <FaFacebook className="text-blue-600 shrink-0" />
                                                    <span className="line-clamp-1">{group.group_name}</span>
                                                </div>
                                                <div className="text-[11px] text-slate-400 mt-0.5">{group.url}</div>
                                            </td>

                                            <td className="py-3.5 px-4">
                                                {group.intent ? (
                                                    <p className="w-max px-2.5 py-1 bg-slate-100 text-slate-700 font-medium rounded-lg text-xs border border-slate-200/60">
                                                        {group.intent}
                                                    </p>
                                                ) : (
                                                    <p className="text-xs text-slate-400 italic">Mặc định</p>
                                                )}
                                            </td>

                                            <td className="py-3.5 px-4 font-medium text-slate-700">{group.members?.toLocaleString() || 0}</td>
                                            <td className="py-3.5 px-4">{renderHealthScore(group.health_score || 0, group.status)}</td>
                                            <td className="py-3.5 px-4">{renderStatusBadge(group.status)}</td>
                                            
                                            {/* ✅ RENDER DỮ LIỆU CỘT CRAWL GẦN NHẤT TRỎ VÀO Carawl_date */}
                                            <td className="py-3.5 px-4">
                                                {group.last_crawl ? formatCrawlDate(group.last_crawl) : <span className="text-slate-400 italic">Chưa crawl</span>}
                                            </td>

                                            <td className="py-3.5 px-4 text-center">
                                                {group.chay_24h ? (
                                                    <span className="px-2 py-0.5 bg-violet-100 text-violet-700 font-bold rounded text-[10px]">TRUE</span>
                                                ) : (
                                                    <span className="px-2 py-0.5 bg-slate-100 text-slate-400 font-bold rounded text-[10px]">FALSE</span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })
                            )}

                            {!isLoadingGroups && presetGroups.length === 0 && !errorGroups && (
                                <tr>
                                    <td colSpan={8} className="py-12 text-center text-slate-400 italic">
                                        Chưa có Facebook Group nào được lưu trữ trên hệ thống.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                {/* FOOTER */}
                <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex items-center justify-between">
                    <div className="text-xs text-slate-500">
                        Đã chọn: <span className="font-bold text-violet-600">{selectedIndices.length}</span> group
                    </div>

                    <div className="flex gap-3">
                        <button type="button" onClick={onClose} className="px-5 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-200/60 rounded-xl border border-slate-200 transition">
                            Hủy
                        </button>
                        <button type="button" disabled={selectedIndices.length === 0 || isLoadingGroups} onClick={handleConfirmSelection} className="px-6 py-2.5 text-sm font-medium text-white bg-violet-600 hover:bg-violet-700 rounded-xl transition disabled:opacity-50 shadow-md shadow-violet-100">
                            Nhập vào Form
                        </button>
                    </div>
                </div>

            </div>
        </div>
    );
}