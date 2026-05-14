// src/modules/group/components/DashboardGroups.tsx
"use client";

import React, { useState, useEffect } from "react";
import { FaFacebook, FaLinkedin } from "react-icons/fa";
import { useGetPresetGroups } from "../hooks/useGetPresetGroups";
import CreateGroupModal from "./CreateGroup_form";

import { FacebookGroupDTO } from "../types/dataFb.type";

const parseBackendDate = (dateInput?: string | Date | null): Date | null => {
    if (!dateInput) return null;
    if (dateInput instanceof Date) return dateInput;

    // Chuyển "2026-05-14 15:30:00" -> "2026-05-14T15:30:00" chuẩn ISO
    const safeDateStr = dateInput.replace(" ", "T");
    const parsedDate = new Date(safeDateStr);

    return isNaN(parsedDate.getTime()) ? null : parsedDate;
};

// Kiểm tra xem ngày crawl có nằm trong 7 ngày qua (1 tuần) hay không
const isWithinLastWeek = (dateInput?: string | Date | null) => {
    const crawlDate = parseBackendDate(dateInput);
    if (!crawlDate) return false;

    const now = new Date();
    const diffTime = now.getTime() - crawlDate.getTime();
    const diffDays = diffTime / (1000 * 60 * 60 * 24);

    return diffDays <= 7; // Trong vòng 1 tuần
};

export function DashboardGroups() {
    const [searchTerm, setSearchTerm] = useState<string>("");
    const [platformFilter, setPlatformFilter] = useState<string>("all");
    const [statusFilter, setStatusFilter] = useState<string>("all");

    // State phân trang
    const [currentPage, setCurrentPage] = useState<number>(1);
    const itemsPerPage = 6;

    const { presetGroups, isLoadingGroups, errorGroups, fetchPresetGroups } = useGetPresetGroups();

    useEffect(() => {
        fetchPresetGroups();
    }, [fetchPresetGroups]);

    // Reset về trang 1 khi các tiêu chí lọc thay đổi
    useEffect(() => {
        setCurrentPage(1);
    }, [searchTerm, platformFilter, statusFilter]);

    // ==========================================
    // 1. TÍNH TOÁN CÁC CHỈ SỐ THỐNG KÊ (SUMMARY CARDS)
    // ==========================================
    const totalPostsIn3Weeks = presetGroups
        .filter(g => isWithinLastWeek(g.date_crawl))
        .reduce((sum, g) => sum + (g.posts_per_week || 0), 0);
    const activeGroups = presetGroups.filter(g => g.status === "ACTIVE").length;
    const totalPostsPerWeek = presetGroups.reduce((sum, g) => sum + (g.posts_per_week || 0), 0);
    const deadGroupsCount = presetGroups.filter(g => g.status === "DEAD").length;

    // ==========================================
    // 2. HELPERS RENDER GIAO DIỆN
    // ==========================================
    const detectPlatform = (url: string) => {
        if (url.includes("linkedin.com")) return "LinkedIn";
        return "Facebook";
    };

    const renderPlatformIcon = (platform: string) => {
        if (platform === "LinkedIn") {
            return <FaLinkedin className="text-blue-700 text-base shrink-0" />;
        }
        return <FaFacebook className="text-blue-600 text-base shrink-0" />;
    };

    const renderHealthScore = (score: number, status?: "ACTIVE" | "IDLE" | "DEAD" | null) => {
        let bgColor = "bg-rose-500";
        let textColor = "text-rose-500";

        if (status === "ACTIVE") {
            bgColor = "bg-emerald-500";
            textColor = "text-emerald-500";
        } else if (status === "IDLE") {
            bgColor = "bg-amber-500";
            textColor = "text-amber-500";
        }

        const progressWidth = Math.min(Math.max(score, 0), 100);

        return (
            <div className="flex items-center gap-3">
                <div className="w-12 h-1.5 bg-slate-100 rounded-full overflow-hidden">
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
        if (!status) return <span className="text-slate-400 italic text-xs">Chưa rõ</span>;

        switch (status) {
            case "ACTIVE":
                return (
                    <span className="px-3 py-1 bg-emerald-50 text-emerald-600 border border-emerald-100 rounded-full text-xs font-medium flex items-center gap-1.5 w-max">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        Sống
                    </span>
                );
            case "IDLE":
                return (
                    <span className="px-3 py-1 bg-amber-50 text-amber-600 border border-amber-100 rounded-full text-xs font-medium flex items-center gap-1.5 w-max">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                        Ít HĐ
                    </span>
                );
            case "DEAD":
                return (
                    <span className="px-3 py-1 bg-rose-50 text-rose-600 border border-rose-100 rounded-full text-xs font-medium flex items-center gap-1.5 w-max">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                        Chết
                    </span>
                );
        }
    };

    // ==========================================
    // 3. LỌC VÀ PHÂN TRANG DỮ LIỆU
    // ==========================================
    const filteredGroups = presetGroups.filter((group) => {
        const platform = detectPlatform(group.url);
        const matchSearch = (group.group_name || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
            (group.url || "").toLowerCase().includes(searchTerm.toLowerCase());
        const matchPlatform = platformFilter === "all" || platform.toLowerCase() === platformFilter.toLowerCase();
        const matchStatus = statusFilter === "all" || (group.status || "").toLowerCase() === statusFilter.toLowerCase();

        return matchSearch && matchPlatform && matchStatus;
    });

    // Tính toán tổng số trang
    const totalPages = Math.ceil(filteredGroups.length / itemsPerPage);

    // Cắt mảng dữ liệu cho trang hiện tại
    const paginatedGroups = filteredGroups.slice(
        (currentPage - 1) * itemsPerPage,
        currentPage * itemsPerPage
    );

    // Thuật toán tạo dải 5 nút phân trang dạng trượt (Sliding Window)
    const getPaginationNumbers = () => {
        const maxButtons = 5;
        let start = Math.max(1, currentPage - 2);
        let end = Math.min(totalPages, currentPage + 2);

        if (totalPages > maxButtons) {
            // Nếu bị sát dải đầu (trang 1, 2)
            if (currentPage <= 3) {
                start = 1;
                end = maxButtons;
            }
            // Nếu bị sát dải cuối
            else if (currentPage >= totalPages - 2) {
                start = totalPages - maxButtons + 1;
                end = totalPages;
            }
        } else {
            start = 1;
            end = totalPages;
        }

        const pages = [];
        for (let i = start; i <= end; i++) {
            pages.push(i);
        }
        return { pages, start, end };
    };
    const [isCreateOpen, setIsCreateOpen] = useState(false);

    const { pages: pageNumbers, start: startPage, end: endPage } = getPaginationNumbers();

    return (
        <div className="w-full max-w-7xl mx-auto p-6 bg-slate-50/50 min-h-screen font-sans">

            {/* THỐNG KÊ TỔNG QUAN */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-100 border-l-4 border-l-violet-500">
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Tổng Groups</p>
                    <h3 className="text-3xl font-black text-slate-800 mt-1">{totalPostsIn3Weeks}</h3>
                    <p className="text-xs text-emerald-600 font-medium mt-2">↑  tuần này</p>
                </div>
                <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-100 border-l-4 border-l-emerald-500">
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Đang Sống</p>
                    <h3 className="text-3xl font-black text-slate-800 mt-1">{activeGroups}</h3>
                    <p className="text-xs text-emerald-600 font-medium mt-2">↑ 2 tuần trước</p>
                </div>
                <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-100 border-l-4 border-l-amber-500">
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Post mới / Tuần</p>
                    <h3 className="text-3xl font-black text-slate-800 mt-1">{totalPostsPerWeek}</h3>
                    <p className="text-xs text-emerald-600 font-medium mt-2">↑ 18%</p>
                </div>
                <div className="bg-white p-5 rounded-xl shadow-sm border border-slate-100 border-l-4 border-l-rose-500">
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Cần Check</p>
                    <h3 className="text-3xl font-black text-slate-800 mt-1">{deadGroupsCount}</h3>
                    <p className="text-xs text-rose-500 font-medium mt-2">↑ 1 hôm nay</p>
                </div>
            </div>

            {/* BẢNG DANH SÁCH GROUPS */}
            <div className="flex items-center justify-end mb-4">
                <button className="bg-violet-500 hover:bg-violet-600 text-white py-2 px-4 rounded-lg text-sm font-medium transition"
                    onClick={() => setIsCreateOpen(true)}
                >
                    + Thêm Group Mới
                </button>
            </div>
            <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden flex flex-col">

                {/* THANH TÌM KIẾM & BỘ LỌC */}
                <div className="p-5 border-b border-slate-100 flex flex-col md:flex-row items-center justify-between gap-4 bg-white">
                    <h2 className="text-base font-bold text-slate-800 self-start md:self-center">Danh sách Groups</h2>

                    <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
                        <div className="relative flex-1 md:w-60">
                            <input
                                type="text"
                                placeholder="🔍 Tìm group..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs outline-none focus:border-violet-500 transition"
                            />
                        </div>
                        <select
                            value={platformFilter}
                            onChange={(e) => setPlatformFilter(e.target.value)}
                            className="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-600 outline-none focus:border-violet-500 cursor-pointer"
                        >
                            <option value="all">Tất cả platform</option>
                            <option value="facebook">Facebook</option>
                            <option value="linkedin">LinkedIn</option>
                        </select>
                        <select
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                            className="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-600 outline-none focus:border-violet-500 cursor-pointer"
                        >
                            <option value="all">Tất cả trạng thái</option>
                            <option value="active">Sống</option>
                            <option value="idle">Ít HĐ</option>
                            <option value="dead">Chết</option>
                        </select>
                    </div>
                </div>

                {/* THÔNG BÁO LỖI NẾU CÓ */}
                {errorGroups && (
                    <div className="m-4 p-3 bg-red-50 border border-red-200 text-red-600 rounded-lg text-xs font-medium">
                        {errorGroups}
                    </div>
                )}

                {/* BẢNG DỮ LIỆU */}
                <div className="overflow-x-auto flex-1">
                    <table className="w-full border-collapse text-left">
                        <thead className="bg-slate-50/75 border-b border-slate-100 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                            <tr>
                                <th className="py-3 px-5">Tên Group</th>
                                <th className="py-3 px-4">Platform</th>
                                <th className="py-3 px-4">Thành viên</th>
                                <th className="py-3 px-4">Post/Tuần</th>
                                <th className="py-3 px-4">Health Score</th>
                                <th className="py-3 px-4">Trạng thái</th>
                                <th className="py-3 px-4">Crawl gần nhất</th>
                                <th className="py-3 px-5 text-center">Hành động</th>
                            </tr>
                        </thead>

                        <tbody className="divide-y divide-slate-100 text-xs text-slate-600">
                            {isLoadingGroups ? (
                                <tr>
                                    <td colSpan={8} className="py-12 text-center text-slate-400">
                                        <div className="flex items-center justify-center gap-2">
                                            <div className="w-5 h-5 border-2 border-violet-600 border-t-transparent rounded-full animate-spin" />
                                            <span>Đang tải dữ liệu...</span>
                                        </div>
                                    </td>
                                </tr>
                            ) : paginatedGroups.length === 0 ? (
                                <tr>
                                    <td colSpan={8} className="py-12 text-center text-slate-400 italic">
                                        Không tìm thấy Group nào phù hợp.
                                    </td>
                                </tr>
                            ) : (
                                paginatedGroups.map((group, index) => {
                                    const platform = detectPlatform(group.url);
                                    const isDead = group.status === "DEAD";

                                    return (
                                        <tr key={index} className="hover:bg-slate-50/50 transition duration-150">
                                            <td className="py-4 px-5 max-w-[250px]">
                                                <div className="font-bold text-slate-900 truncate">
                                                    {group.group_name}
                                                </div>
                                                <a
                                                    href={group.url.startsWith('http') ? group.url : `https://${group.url}`}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-[11px] text-slate-400 hover:text-blue-600 hover:underline truncate block mt-0.5"
                                                >
                                                    {group.url.replace(/^https?:\/\//, '')}
                                                </a>
                                            </td>
                                            <td className="py-4 px-4 font-medium text-slate-700">
                                                <div className="flex items-center gap-2">
                                                    {renderPlatformIcon(platform)}
                                                    <span>{platform}</span>
                                                </div>
                                            </td>
                                            <td className="py-4 px-4 font-medium text-slate-700">
                                                {group.members?.toLocaleString() || "0"}
                                            </td>
                                            <td className="py-4 px-4 font-medium text-slate-700">
                                                {group.posts_per_week?.toLocaleString() || "0"}
                                            </td>
                                            <td className="py-4 px-4">
                                                {renderHealthScore(group.health_score || 0, group.status)}
                                            </td>
                                            <td className="py-4 px-4">
                                                {renderStatusBadge(group.status)}
                                            </td>
                                            <td className="py-4 px-4 text-slate-600">
                                                {group.last_crawl || <span className="italic text-slate-400">Chưa crawl</span>}
                                            </td>
                                            <td className="py-4 px-5 text-center">
                                                {isDead ? (
                                                    <button
                                                        disabled
                                                        className="px-3 py-1.5 bg-rose-50 text-rose-500 font-medium rounded-lg text-xs border border-rose-100 cursor-not-allowed"
                                                    >
                                                        Vô hiệu
                                                    </button>
                                                ) : (
                                                    <button
                                                        onClick={() => window.open(group.url, "_blank")}
                                                        className="px-3 py-1.5 bg-white text-violet-600 hover:bg-violet-50 font-medium rounded-lg text-xs border border-violet-200 transition"
                                                    >
                                                        Xem posts
                                                    </button>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })
                            )}
                        </tbody>
                    </table>
                </div>

                {/* FOOTER PHÂN TRANG */}
                {!isLoadingGroups && totalPages > 1 && (
                    <div className="p-4 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3 bg-white">
                        <div className="text-xs text-slate-500">
                            Hiển thị <span className="font-bold text-slate-700">{((currentPage - 1) * itemsPerPage) + 1}</span> - <span className="font-bold text-slate-700">{Math.min(currentPage * itemsPerPage, filteredGroups.length)}</span> trong số <span className="font-bold text-slate-700">{filteredGroups.length}</span> groups
                        </div>

                        <div className="flex items-center gap-1">
                            {/* Nút Previous */}
                            <button
                                onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                                disabled={currentPage === 1}
                                className="px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition disabled:opacity-40 disabled:hover:bg-transparent"
                            >
                                Trước
                            </button>

                            {/* Dấu ... ở đầu nếu dải trang hiển thị không bắt đầu từ 1 */}
                            {startPage > 1 && (
                                <>
                                    <button
                                        onClick={() => setCurrentPage(1)}
                                        className="w-7 h-7 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition"
                                    >
                                        1
                                    </button>
                                    {startPage > 2 && <span className="px-1 text-slate-400 text-xs">...</span>}
                                </>
                            )}

                            {/* Các nút số trong sliding window */}
                            {pageNumbers.map(page => (
                                <button
                                    key={page}
                                    onClick={() => setCurrentPage(page)}
                                    className={`w-7 h-7 text-xs font-medium rounded-lg transition ${currentPage === page
                                            ? "bg-violet-600 text-white font-bold shadow-sm shadow-violet-200"
                                            : "text-slate-600 hover:bg-slate-100"
                                        }`}
                                >
                                    {page}
                                </button>
                            ))}

                            {/* Dấu ... ở cuối nếu dải trang hiển thị chưa tới trang cuối */}
                            {endPage < totalPages && (
                                <>
                                    {endPage < totalPages - 1 && <span className="px-1 text-slate-400 text-xs">...</span>}
                                    <button
                                        onClick={() => setCurrentPage(totalPages)}
                                        className="w-7 h-7 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition"
                                    >
                                        {totalPages}
                                    </button>
                                </>
                            )}

                            {/* Nút Next */}
                            <button
                                onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                                disabled={currentPage === totalPages}
                                className="px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition disabled:opacity-40 disabled:hover:bg-transparent"
                            >
                                Sau
                            </button>
                        </div>
                    </div>
                )}

            </div>
            <CreateGroupModal 
                isOpen={isCreateOpen} 
                onClose={() => setIsCreateOpen(false)} 
            />
        </div>
    );
}