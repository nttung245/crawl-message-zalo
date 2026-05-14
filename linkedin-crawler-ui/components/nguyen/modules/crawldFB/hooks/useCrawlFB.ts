import { useState, useRef } from "react";
import { toast } from "sonner"; // Import sonner
import { CrawlFBRequest, GroupSummaryType } from "../types/crawlFB_type";
import { CrawlFb_form } from "../schemas/crawlFb_schemas";

export const useCrawlFB = () => {
    const [isLoading, setIsLoading] = useState<boolean>(false);
    const [loadingMsg, setLoadingMsg] = useState<string>("Đang kết nối đến máy chủ...");
    const [result, setResult] = useState<GroupSummaryType[] | null>();

    // Dùng ref để lưu trữ instance WebSocket nhằm gọi đóng kết nối (Hủy) khi cần
    const wsRef = useRef<WebSocket | null>(null);

    const getWsUrl = (email: string) => {
        const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "";
        let wsUrl = "";

        if (baseUrl.startsWith("http")) {
            // Thay http thành ws, https thành wss
            wsUrl = baseUrl.replace(/^http/, "ws");
        } else {
            // Nếu baseUrl là relative path
            const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            wsUrl = `${protocol}//${window.location.host}${baseUrl}`;
        }
        return `${wsUrl}/ws/CrawlFbForFE/${encodeURIComponent(email)}`;
    };

    const submitCrawlData = (data: CrawlFb_form) => {
        // Tạo định danh duy nhất (email) cho kết nối WS
        const emailId = data.isDefaultAccount ? `default_user_${Date.now()}` : (data.userName || "anonymous");

        setIsLoading(true);
        setLoadingMsg("Đang kết nối đến máy chủ...");
        setResult(null);

        const payload: CrawlFBRequest = {
            groups: data.rows,
            tkFB: {
                useName: data.isDefaultAccount ? "" : data.userName,
                password: data.isDefaultAccount ? "" : data.password,
            }
        }

        const wsUrl = getWsUrl(emailId);
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            // Gửi dữ liệu yêu cầu ngay khi mở luồng WebSocket
            ws.send(JSON.stringify(payload));
        };

        ws.onmessage = (event) => {
            try {
                const response = JSON.parse(event.data);
                console.log("WS Response:", response); // <--- THÊM DÒNG NÀY ĐỂ DEBUG

                if (response.status === "queued" || response.status === "processing") {
                    setLoadingMsg(response.message);
                    toast.info(response.message, { id: "ws-status" });
                }
                else if (response.status === "success") {
                    setIsLoading(false); // <--- CHỦ ĐỘNG TẮT LOADING TẠI ĐÂY

                    if (response.data && response.data.length > 0) {
                        setResult(response.data);
                        toast.success("Crawl thành công!", { id: "ws-status" });
                    } else {
                        setResult([]);
                        toast.info("Crawl hoàn tất nhưng không tìm thấy dữ liệu mới.", { id: "ws-status" });
                    }
                    ws.close();
                }
                else if (response.status === "error" || response.status === "fail") {
                    setIsLoading(false); // <--- CHỦ ĐỘNG TẮT LOADING TẠI ĐÂY
                    toast.error(response.message || "Lỗi trích xuất dữ liệu từ Server", { id: "ws-status" });
                    ws.close();
                }
            } catch (error) {
                console.error("Lỗi khi parse message từ WebSocket:", error);
                setIsLoading(false); // Tắt loading nếu parse JSON lỗi
            }
        };

        ws.onerror = (error) => {
            console.error("Lỗi WebSocket Crawl FB:", error);
            toast.error("Mất kết nối WebSocket với máy chủ!");
            setIsLoading(false);
        };

        ws.onclose = () => {
            // Tự động tắt loading khi socket đóng
            setIsLoading(false);
        };
    };

    const cancelCrawl = () => {
        if (wsRef.current) {
            // Đóng WebSocket từ phía client sẽ gọi WebSocketDisconnect phía Backend (ngắt Playwright)
            wsRef.current.close();
            wsRef.current = null;

            toast.error("Đã hủy quá trình cào dữ liệu!");
            setIsLoading(false);
        }
    };

    return {
        isLoading,
        loadingMsg,
        submitCrawlData,
        result,
        cancelCrawl
    };
};