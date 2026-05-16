// src/modules/interaction/components/InteractionUI.tsx
"use client";

import React, { useEffect, useMemo } from "react";
import { useGetInteractions } from "../hooks/useGetInteraction";

export function InteractionUI() {
    const { interactions, isLoading, error, fetchInteractions } = useGetInteractions();

    useEffect(() => {
        fetchInteractions();
    }, [fetchInteractions]);

    const getInitials = (name: string) => {
        const words = name.trim().split(" ");
        if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
        return name.substring(0, 2).toUpperCase();
    };

    const renderRankIcon = (index: number) => {
        if (index === 0) return <span className="text-2xl drop-shadow-md">🥇</span>;
        if (index === 1) return <span className="text-2xl drop-shadow-md">🥈</span>;
        if (index === 2) return <span className="text-2xl drop-shadow-md">🥉</span>;
        return <span className="text-slate-400 font-semibold w-8 text-center">{index + 1}</span>;
    };

    // ==========================================
    // TÍNH TOÁN DỮ LIỆU CHO CÁC THẺ THỐNG KÊ
    // ==========================================
    const stats = useMemo(() => {
        if (!interactions || interactions.length === 0) {
            return { total: 0, avgScore: 0, active: 0, topUser: null };
        }

        const total = interactions.length;
        const totalScore = interactions.reduce((sum, user) => sum + (user.scorePerWeek || 0), 0);
        const avgScore = Math.round(totalScore / total);
        const active = interactions.filter(u => u.scorePerWeek > 0).length;
        
        const topUser = interactions.reduce((max, user) => 
            (user.scorePerWeek > max.scorePerWeek ? user : max), interactions[0]
        );

        return { total, avgScore, active, topUser };
    }, [interactions]);

    return (
        <div className="w-full max-w-6xl mx-auto p-6 bg-slate-50 min-h-screen">
            
            {/* HEADER */}
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-bold text-slate-700 uppercase tracking-wide">
                    Thống Kê Tương Tác
                </h2>
                <button 
                    onClick={fetchInteractions}
                    disabled={isLoading}
                    className="text-sm px-4 py-2 bg-white border border-slate-200 text-slate-600 font-medium rounded-lg hover:bg-slate-100 transition disabled:opacity-50 shadow-sm"
                >
                    {isLoading ? "Đang tải..." : "Làm mới"}
                </button>
            </div>

            {error && (
                <div className="mb-4 p-4 bg-red-50 text-red-600 rounded-xl border border-red-100 text-sm font-medium">
                    {error}
                </div>
            )}

            {/* ========================================== */}
            {/* KHỐI OVERVIEW THỐNG KÊ MỚI (STYLE BORDER LEFT) */}
            {/* ========================================== */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                
                {/* Thẻ 1: Tổng Users (Viền Tím) */}
                <div className="bg-white rounded-lg shadow-sm border border-slate-100 p-5 border-l-[6px] border-l-violet-500">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
                        Tổng Users
                    </h3>
                    <div className="text-3xl font-black text-slate-800">
                        {isLoading ? "-" : stats.total}
                    </div>
                    <div className="text-xs text-emerald-600 font-medium mt-2">
                        ↑ tuần này
                    </div>
                </div>

                {/* Thẻ 2: Score Trung Bình (Viền Xanh Lá) */}
                <div className="bg-white rounded-lg shadow-sm border border-slate-100 p-5 border-l-[6px] border-l-emerald-500">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
                        Score Trung Bình
                    </h3>
                    <div className="text-3xl font-black text-slate-800">
                        {isLoading ? "-" : stats.avgScore}
                    </div>
                    <div className="text-xs text-emerald-600 font-medium mt-2">
                        ↑ {stats.active}/{stats.total} có data
                    </div>
                </div>

              

                {/* Thẻ 4: Top Tương Tác (Viền Đỏ Hồng) */}
                <div className="bg-white rounded-lg shadow-sm border border-slate-100 p-5 border-l-[6px] border-l-rose-500 overflow-hidden">
                    <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">
                        Top Hôm Nay
                    </h3>
                    <div className="text-2xl font-black text-slate-800 truncate" title={stats.topUser?.name || ""}>
                        {isLoading ? "-" : (stats.topUser?.name || "-")}
                    </div>
                    <div className="text-xs text-green-500 font-medium mt-2">
                        ↑ Score: {stats.topUser?.scorePerWeek || 0}
                    </div>
                </div>

            </div>

            {/* ========================================== */}
            {/* DANH SÁCH BẢNG XẾP HẠNG INTERACTION */}
            {/* ========================================== */}
            <div className="flex flex-col gap-3 relative">
                {isLoading && interactions.length === 0 ? (
                    <div className="p-12 flex justify-center">
                        <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
                    </div>
                ) : (
                    interactions.map((user, index) => {
                        const progressWidth = Math.min(Math.max(user.scorePerWeek, 0), 100);

                        return (
                            <div 
                                key={user.id} 
                                className="bg-white rounded-xl border border-slate-200 p-4 flex items-center gap-4 hover:shadow-md transition-shadow duration-200 relative overflow-hidden group"
                            >
                                <div className="flex items-center justify-center w-10 shrink-0">
                                    {renderRankIcon(index)}
                                </div>

                                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shrink-0
                                    ${index === 0 ? 'bg-amber-100 text-amber-700' : 
                                      index === 1 ? 'bg-slate-100 text-slate-700' : 
                                      index === 2 ? 'bg-orange-100 text-orange-700' : 'bg-violet-50 text-violet-600'}`}
                                >
                                    {getInitials(user.name)}
                                </div>

                                <div className="flex-1 min-w-0 flex flex-col justify-center">
                                    <div className="font-bold text-slate-800 text-[15px] truncate mb-1">
                                        {user.name}
                                    </div>
                                    <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden mt-1">
                                        <div 
                                            className={`h-full rounded-full transition-all duration-1000 ease-out
                                                ${index < 3 ? 'bg-emerald-500' : 'bg-amber-500'}`}
                                            style={{ width: `${progressWidth}%` }}
                                        />
                                    </div>
                                </div>

                                <div className="flex flex-col items-end shrink-0 pl-4 border-l border-slate-100">
                                    <span className={`text-xl font-bold 
                                        ${index === 0 ? 'text-emerald-600' : 
                                          index === 1 ? 'text-emerald-500' : 
                                          index === 2 ? 'text-emerald-400' : 'text-amber-600'}`}
                                    >
                                        {user.scorePerWeek}
                                    </span>
                                    <span className="text-[10px] uppercase font-medium text-slate-400 tracking-wider mt-0.5">
                                        AI Score
                                    </span>
                                </div>
                            </div>
                        );
                    })
                )}
                
                {!isLoading && interactions.length === 0 && !error && (
                    <div className="p-12 text-center text-slate-400 italic bg-white rounded-xl border border-slate-200">
                        Chưa có dữ liệu tương tác trong tuần này.
                    </div>
                )}
            </div>
        </div>
    );
}