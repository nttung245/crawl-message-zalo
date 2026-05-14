// src/modules/post/components/DashboardPosts.tsx
"use client";

import React, { useState, useEffect } from "react";
import { FaFacebook, FaLinkedin } from "react-icons/fa";
import { useGetIntents } from "../hooks/useGetIntents"; 
import { useFetchAllPosts } from "../hooks/useGetDataFb"; 
import { DataFBResponse } from "../types/dataFb.type"; 
import { PostCard } from "./dataFbCard_component";

// ============================================================================
// 1. CÁC HÀM HELPER PURE (ĐẶT NGOÀI COMPONENT)
// Giải quyết triệt để lỗi TDZ (Cannot access before initialization) và tối ưu RAM
// ============================================================================

// Nhận diện nền tảng mạng xã hội dựa trên URL
const detectPlatform = (post: DataFBResponse) => {
    const targetUrl = post.link_group || post.url || "";
    return targetUrl.includes("linkedin.com") ? "LinkedIn" : "Facebook";
};

// Render Icon Platform tương ứng
const renderPlatformIcon = (platform: string) => {
    if (platform === "LinkedIn") {
        return <FaLinkedin className="text-blue-700 text-xs shrink-0" title="LinkedIn" />;
    }
    return <FaFacebook className="text-blue-600 text-xs shrink-0" title="Facebook" />;
};

// Trích xuất chuỗi 10 ký tự ngày chuẩn (YYYY-MM-DD) từ string hoặc Date Object
const getDatePart = (dateInput?: Date | string | null) => {
    if (!dateInput) return "";
    if (typeof dateInput === "string") {
        return dateInput.substring(0, 10);
    }
    try {
        return dateInput.toISOString().split("T")[0];
    } catch (e) {
        return "";
    }
};

// Trích xuất chuỗi ngày hiển thị thân thiện (DD/MM/YYYY)
const getCompactDateString = (dateInput?: Date | string | null) => {
    if (!dateInput) return "";
    try {
        if (dateInput instanceof Date) {
            return dateInput.toLocaleDateString('vi-VN');
        }
        const safeStr = dateInput.replace(" ", "T");
        return new Date(safeStr).toLocaleDateString('vi-VN');
    } catch (e) {
        return "";
    }
};

// Chuyển đổi dữ liệu thời gian sang dạng số (Timestamp) để phục vụ sắp xếp mới nhất
const getDateTimestamp = (dateInput?: Date | string | null) => {
    if (!dateInput) return 0;
    try {
        if (dateInput instanceof Date) return dateInput.getTime();
        return new Date(dateInput.replace(" ", "T")).getTime();
    } catch (e) {
        return 0;
    }
};

// Render UI động hiển thị so sánh chênh lệch giữa 2 mốc số liệu
const renderComparisonUI = (todayCount: number, yesterdayCount: number) => {
    const diff = todayCount - yesterdayCount;
    
    if (diff > 0) {
        return (
            <p className="text-xs text-emerald-600 font-medium mt-3">
                ↑ {diff} so với hôm qua
            </p>
        );
    } else if (diff < 0) {
        return (
            <p className="text-xs text-rose-500 font-medium mt-3">
                ↓ {Math.abs(diff)} so với hôm qua
            </p>
        );
    }
    return (
        <p className="text-xs text-slate-400 font-medium mt-3">
            ↔ Bằng với hôm qua
        </p>
    );
};

// ============================================================================
// 2. COMPONENT CHÍNH
// ============================================================================
export function DashboardPosts() {
    // States bộ lọc & sắp xếp
    const [searchTerm, setSearchTerm] = useState<string>("");
    const [intentFilter, setIntentFilter] = useState<string>("all");
    const [platformFilter, setPlatformFilter] = useState<string>("all");
    const [sortBy, setSortBy] = useState<string>("latest"); 

    // States phân trang
    const [currentPage, setCurrentPage] = useState<number>(1);
    const itemsPerPage = 6;

    // State lưu trữ dữ liệu bài viết đang được mở trong Modal
    const [selectedPostForModal, setSelectedPostForModal] = useState<DataFBResponse | null>(null);

    // Gọi Hooks fetch dữ liệu
    const { intents, fetchIntents } = useGetIntents();
    const { allPosts, isLoading, error, refetch } = useFetchAllPosts();

    // Tự động tải danh sách Intents khi mount
    useEffect(() => {
        fetchIntents();
    }, [fetchIntents]);

    // Tự động quay về trang 1 nếu thay đổi từ khóa tìm kiếm hoặc các bộ lọc
    useEffect(() => {
        setCurrentPage(1);
    }, [searchTerm, intentFilter, platformFilter, sortBy]);

    // Helper render Intent Badge (Sử dụng danh sách intents lấy từ API)
    const renderIntentBadge = (intentValue?: string) => {
        if (!intentValue) return null;

        const matched = intents.find(i => i.value === intentValue || i.name === intentValue);
        const displayName = matched ? matched.name : intentValue;
        const normalized = displayName.toLowerCase();


        return (
            <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-medium border flex items-center gap-1 w-max bg-blue-50 text-blue-600 border-blue-100`}>
               
                <span>{displayName}</span>
            </span>
        );
    };

    // ==========================================
    // TÍNH TOÁN CÁC CHỈ SỐ THỐNG KÊ (SUMMARY CARDS)
    // ==========================================
    // Xác định mốc ngày hệ thống chuẩn
    const todayStr = new Date().toISOString().split("T")[0];
    
    const yesterdayObj = new Date();
    yesterdayObj.setDate(yesterdayObj.getDate() - 1);
    const yesterdayStr = yesterdayObj.toISOString().split("T")[0];

    // Lọc tập dữ liệu cào về trong Hôm nay và Hôm qua
    const postsToday = allPosts.filter(p => getDatePart(p.dateCrawl) === todayStr);
    const postsYesterday = allPosts.filter(p => getDatePart(p.dateCrawl) === yesterdayStr);

    const totalPostsToday = postsToday.length;
    const totalPostsYesterday = postsYesterday.length;

    const highScores = allPosts.filter(p => p.score >= 70);
    const highScorePercent = allPosts.length > 0 ? Math.round((highScores.length / allPosts.length) * 100) : 0;
    
    const pendingReviewCount = allPosts.filter(p => p.score >= 50 && p.score < 70).length;
    
    // Giả định dữ liệu seeded chiếm 20% lượng bài thu thập của mỗi ngày
    const seededTodayCount = Math.floor(totalPostsToday * 0.2); 
    const seededYesterdayCount = Math.floor(totalPostsYesterday * 0.2);

    // ==========================================
    // LỌC & SẮP XẾP DỮ LIỆU
    // ==========================================
    let filteredPosts = allPosts.filter((post) => {
        const platform = detectPlatform(post);
        
        const matchSearch = (post.content || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
                            (post.group_name || "").toLowerCase().includes(searchTerm.toLowerCase());
        
        const matchIntent = intentFilter === "all" || 
                            (intentFilter === "unclassified" && !post.intent) ||
                            (post.intent || "").toLowerCase() === intentFilter.toLowerCase();
        
        const matchPlatform = platformFilter === "all" || platform.toLowerCase() === platformFilter.toLowerCase();

        return matchSearch && matchIntent && matchPlatform;
    });

    // Thực thi sắp xếp danh sách
    filteredPosts.sort((a, b) => {
        if (sortBy === "score_desc") return b.score - a.score;
        if (sortBy === "score_asc") return a.score - b.score;
        if (sortBy === "comments_desc") return (b.comments || 0) - (a.comments || 0);
        if (sortBy === "latest") {
            return getDateTimestamp(b.dateCrawl) - getDateTimestamp(a.dateCrawl);
        }
        return 0;
    });

    // ==========================================
    // LOGIC PHÂN TRANG (SLIDING WINDOW 5 NÚT)
    // ==========================================
    const totalPages = Math.ceil(filteredPosts.length / itemsPerPage);
    const paginatedPosts = filteredPosts.slice(
        (currentPage - 1) * itemsPerPage,
        currentPage * itemsPerPage
    );

    const getPaginationNumbers = () => {
        const maxButtons = 5;
        let start = Math.max(1, currentPage - 2);
        let end = Math.min(totalPages, currentPage + 2);

        if (totalPages > maxButtons) {
            if (currentPage <= 3) {
                start = 1;
                end = maxButtons;
            } else if (currentPage >= totalPages - 2) {
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

    const { pages: pageNumbers, start: startPage, end: endPage } = getPaginationNumbers();

    return (
        <div className="w-full max-w-7xl mx-auto p-6 bg-slate-50 min-h-screen font-sans">
            
            {/* HÀNG 1: 4 THẺ THỐNG KÊ TỔNG QUAN */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                <div className="bg-white p-4 rounded-xl shadow-xs border border-slate-100 border-l-4 border-l-indigo-600 flex flex-col justify-between">
                    <div>
                        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Tổng bài hôm nay</p>
                        <h3 className="text-3xl font-black text-slate-900 mt-1">{totalPostsToday}</h3>
                    </div>
                    {renderComparisonUI(totalPostsToday, totalPostsYesterday)}
                </div>

                <div className="bg-white p-4 rounded-xl shadow-xs border border-slate-100 border-l-4 border-l-emerald-500 flex flex-col justify-between">
                    <div>
                        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Điểm cao (≥70)</p>
                        <h3 className="text-3xl font-black text-slate-900 mt-1">{highScores.length}</h3>
                    </div>
                    <p className="text-xs text-emerald-600 font-medium mt-3">{highScorePercent}% đủ điều kiện</p>
                </div>

                {/* <div className="bg-white p-4 rounded-xl shadow-xs border border-slate-100 border-l-4 border-l-amber-500 flex flex-col justify-between">
                    <div>
                        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Cần Theo Dõi</p>
                        <h3 className="text-3xl font-black text-slate-900 mt-1">{pendingReviewCount}</h3>
                    </div>
                    <p className="text-xs text-amber-600 font-medium mt-3">Điểm mức trung bình</p>
                </div> */}

                <div className="bg-white p-4 rounded-xl shadow-xs border border-slate-100 border-l-4 border-l-purple-600 flex flex-col justify-between">
                    <div>
                        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Đã Seeded hôm nay</p>
                        <h3 className="text-3xl font-black text-slate-900 mt-1">{seededTodayCount}</h3>
                    </div>
                    {renderComparisonUI(seededTodayCount, seededYesterdayCount)}
                </div>
            </div>

            {/* HÀNG 2: THANH CÔNG CỤ TÌM KIẾM & BỘ LỌC */}
            <div className="flex flex-wrap items-center gap-3 mb-6 bg-transparent">
                <div className="relative flex-1 min-w-[220px]">
                    <input 
                        type="text" 
                        placeholder="🔍 Tìm kiếm bài post..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs outline-none focus:border-indigo-600 shadow-xs transition"
                    />
                </div>

                <select 
                    value={intentFilter} 
                    onChange={(e) => setIntentFilter(e.target.value)}
                    className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-700 outline-none focus:border-indigo-600 shadow-xs cursor-pointer"
                >
                    <option value="all">Tất cả intent</option>
                    <option value="unclassified">Chưa phân loại</option>
                    {intents.map((item, idx) => (
                        <option key={idx} value={item.value}>{item.name}</option>
                    ))}
                </select>

                <select 
                    value={platformFilter} 
                    onChange={(e) => setPlatformFilter(e.target.value)}
                    className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-700 outline-none focus:border-indigo-600 shadow-xs cursor-pointer"
                >
                    <option value="all">Tất cả platform</option>
                    <option value="facebook">Facebook</option>
                    <option value="linkedin">LinkedIn</option>
                </select>

                <select 
                    value={sortBy} 
                    onChange={(e) => setSortBy(e.target.value)}
                    className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-700 outline-none focus:border-indigo-600 shadow-xs cursor-pointer font-medium"
                >
                    <option value="latest">Sắp xếp: Mới nhất</option>
                    <option value="score_desc">Sắp xếp: Điểm cao nhất</option>
                    <option value="score_asc">Sắp xếp: Điểm thấp nhất</option>
                    <option value="comments_desc">Sắp xếp: Bình luận nhiều nhất</option>
                </select>

                <button 
                    onClick={refetch}
                    disabled={isLoading}
                    className="px-3 py-2 bg-white border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-lg text-xs font-medium transition cursor-pointer flex items-center gap-1 disabled:opacity-50"
                    title="Làm mới dữ liệu"
                >
                    🔄
                </button>
            </div>

            {/* KHU VỰC THÔNG BÁO LỖI NẾU CÓ */}
            {error && (
                <div className="mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-600 rounded-lg text-xs font-medium">
                    {error}
                </div>
            )}

            {/* HÀNG 3: DANH SÁCH BÀI VIẾT (DẠNG THẺ THU GỌN) */}
            <div className="flex flex-col gap-4">
                {isLoading ? (
                    <div className="py-20 bg-white rounded-xl border border-slate-100 flex flex-col items-center justify-center gap-2">
                        <div className="w-6 h-6 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
                        <span className="text-xs text-slate-400">Đang tải dữ liệu bài viết từ API...</span>
                    </div>
                ) : paginatedPosts.length === 0 ? (
                    <div className="py-20 bg-white rounded-xl border border-slate-100 text-center text-xs text-slate-400 italic">
                        Không tìm thấy bài post nào phù hợp với bộ lọc.
                    </div>
                ) : (
                    paginatedPosts.map((post, index) => {
                        const platform = detectPlatform(post);
                        const compactDateStr = getCompactDateString(post.dateCrawl);

                        // Phân loại màu nền cho Score Box
                        let scoreBg = "bg-slate-100 text-slate-700";
                        if (post.score >= 85) scoreBg = "bg-emerald-100 text-emerald-700";
                        else if (post.score >= 60) scoreBg = "bg-amber-100 text-amber-700";

                        return (
                            <div 
                                key={index} 
                                className="bg-white rounded-xl shadow-xs border border-slate-200/80 p-4 flex gap-4 items-start transition duration-200 hover:border-slate-300"
                            >
                                {/* KHỐI AI SCORE BÊN TRÁI */}
                                <div className={`w-14 h-14 rounded-xl flex flex-col items-center justify-center shrink-0 ${scoreBg}`}>
                                    <span className="text-xl font-black leading-tight">{post.score}</span>
                                    <span className="text-[9px] font-bold text-slate-400 uppercase tracking-tighter mt-0.5">AI Score</span>
                                </div>

                                {/* NỘI DUNG CHÍNH */}
                                <div className="flex-1 flex flex-col justify-between min-w-0">
                                    
                                    <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            {renderPlatformIcon(platform)}

                                            <a 
                                                href={post.link_group || "#"} 
                                                target="_blank" 
                                                rel="noopener noreferrer"
                                                className="text-xs font-bold text-slate-900 hover:text-indigo-600 hover:underline truncate max-w-[220px]"
                                            >
                                                {post.group_name}
                                            </a>

                                            {renderIntentBadge(post.intent)}
                                        </div>

                                        <span className="text-[11px] text-slate-400 shrink-0 font-medium">
                                            {compactDateStr} {post.date ? `• ${post.date}` : ''}
                                        </span>
                                    </div>

                                    {/* TRÍCH DẪN NỘI DUNG */}
                                    <p className="text-xs text-slate-700 italic line-clamp-2 leading-relaxed bg-slate-50/50 p-x-2.5 rounded-lg border border-slate-100/60 mb-3">
                                        "{post.content || "Nội dung bài viết rỗng hoặc chứa thuần hình ảnh/video."}"
                                    </p>

                                    {/* FOOTER THẺ CON */}
                                    <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
                                        
                                        <div className="flex items-center gap-2.5 flex-wrap">
                                            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-amber-50/60 text-amber-700 rounded-md text-[11px] font-bold border border-amber-100/40" title="Lượt thích/Cảm xúc">
                                                👍 {post.reactions?.toLocaleString() || 0}
                                            </span>
                                            
                                            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-100 text-slate-600 rounded-md text-[11px] font-bold" title="Lượt bình luận">
                                                💬 {post.comments?.toLocaleString() || 0}
                                            </span>

                                            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-blue-50 text-blue-600 rounded-md text-[11px] font-bold" title="Lượt chia sẻ">
                                                🔁 {post.shares?.toLocaleString() || 0}
                                            </span>
                                        </div>

                                        {/* KÍCH HOẠT MODAL KHI XEM CHI TIẾT */}
                                        <div className="flex items-center gap-2">
                                            <button
                                                type="button"
                                                onClick={() => setSelectedPostForModal(post)}
                                                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition shadow-xs cursor-pointer"
                                            >
                                                Xem chi tiết
                                            </button>
                                        </div>

                                    </div>

                                </div>
                            </div>
                        );
                    })
                )}
            </div>

            {/* HÀNG 4: FOOTER PHÂN TRANG */}
            {!isLoading && totalPages > 1 && (
                <div className="mt-6 p-4 border border-slate-200/80 rounded-xl flex flex-col sm:flex-row items-center justify-between gap-3 bg-white">
                    <div className="text-xs text-slate-500">
                        Hiển thị <span className="font-bold text-slate-700">{((currentPage - 1) * itemsPerPage) + 1}</span> - <span className="font-bold text-slate-700">{Math.min(currentPage * itemsPerPage, filteredPosts.length)}</span> trong số <span className="font-bold text-slate-700">{filteredPosts.length}</span> bài viết
                    </div>

                    <div className="flex items-center gap-1">
                        <button
                            onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                            disabled={currentPage === 1}
                            className="px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition disabled:opacity-40 disabled:hover:bg-transparent cursor-pointer"
                        >
                            Trước
                        </button>

                        {startPage > 1 && (
                            <>
                                <button
                                    onClick={() => setCurrentPage(1)}
                                    className="w-7 h-7 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition cursor-pointer"
                                >
                                    1
                                </button>
                                {startPage > 2 && <span className="px-1 text-slate-400 text-xs">...</span>}
                            </>
                        )}

                        {pageNumbers.map(page => (
                            <button
                                key={page}
                                onClick={() => setCurrentPage(page)}
                                className={`w-7 h-7 text-xs font-medium rounded-lg transition cursor-pointer ${
                                    currentPage === page 
                                        ? "bg-indigo-600 text-white font-bold shadow-xs" 
                                        : "text-slate-600 hover:bg-slate-100"
                                }`}
                            >
                                {page}
                            </button>
                        ))}

                        {endPage < totalPages && (
                            <>
                                {endPage < totalPages - 1 && <span className="px-1 text-slate-400 text-xs">...</span>}
                                <button
                                    onClick={() => setCurrentPage(totalPages)}
                                    className="w-7 h-7 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition cursor-pointer"
                                >
                                    {totalPages}
                                </button>
                            </>
                        )}

                        <button
                            onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                            disabled={currentPage === totalPages}
                            className="px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-lg transition disabled:opacity-40 disabled:hover:bg-transparent cursor-pointer"
                        >
                            Sau
                        </button>
                    </div>
                </div>
            )}

            {/* ========================================================= */}
            {/* KHOANG RENDER MODAL HIỂN THỊ COMPONENT CON NGUYÊN BẢN */}
            {/* ========================================================= */}
            {selectedPostForModal && (
                <div 
                    className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-in fade-in duration-200"
                    onClick={() => setSelectedPostForModal(null)} 
                >
                    <div 
                        className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl"
                        onClick={(e) => e.stopPropagation()} 
                    >
                        {/* Nút Đóng góc trên */}
                        <div className="absolute top-3 right-3 z-10">
                            <button 
                                onClick={() => setSelectedPostForModal(null)}
                                className="w-8 h-8 flex items-center justify-center rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold transition shadow-xs cursor-pointer"
                                title="Đóng"
                            >
                                ✕
                            </button>
                        </div>

                        {/* TRUYỀN NGUYÊN OBJECT VÀO COMPONENT CON CỦA BẠN */}
                        <PostCard item={selectedPostForModal} />

                    </div>
                </div>
            )}

        </div>
    );
}