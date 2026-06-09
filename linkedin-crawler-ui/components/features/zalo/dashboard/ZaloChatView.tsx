"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { MaterialIcon } from "@/components/ui";
import type { ZaloCrawlerFlowValue } from "@/hooks/useZaloCrawlerFlow";
import {
  getZaloConversationMessages,
  getZaloConversations,
  syncZaloRecentConversations,
  createZaloBroadcast,
  sendZaloMessage,
  sendZaloMessageWithFiles,
  markZaloConversationAsRead,
} from "@/services/zaloCrawlerService";
import type {
  ZaloConversationSummary,
  ZaloLibraryMessage,
  ZaloSyncRecentResponse,
  ZaloBroadcastTarget,
} from "@/types/zalo-api";

const REFRESH_INTERVAL_MS = 2000;
const MESSAGE_PAGE_SIZE = 50;
const SYNC_CONVERSATION_LIMIT = 50;
const SYNC_MESSAGES_PER_CONVERSATION = 50;
const BOTTOM_THRESHOLD_PX = 96;

interface ZaloChatViewProps {
  flow: ZaloCrawlerFlowValue;
  onBackToDashboard: () => void;
}

function formatTime(value?: string | null) {
  if (!value) return "Chưa có";
  const num = Number(value);
  const date = !Number.isNaN(num) && String(num) === String(value).trim() ? new Date(num) : new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function shortId(value: string, head = 10, tail = 6) {
  if (value.length <= head + tail + 3) return value;
  return `${value.slice(0, head)}...${value.slice(-tail)}`;
}

function isFallbackName(name: string | null | undefined, id: string) {
  const cleanName = String(name || "").trim();
  return !cleanName || cleanName === id || cleanName === `Conversation ${id}`;
}

function conversationTitle(conversation: ZaloConversationSummary | null) {
  if (!conversation) return "Chọn một hội thoại";
  if (isFallbackName(conversation.conversation_name, conversation.conversation_id)) {
    return "Hội thoại chưa đặt tên";
  }
  return conversation.conversation_name;
}

function initials(value: string) {
  const words = value
    .replace(/^\[|\]$/g, "")
    .split(/\s+/)
    .filter(Boolean);
  const first = words[0]?.[0] ?? "Z";
  const second = words.length > 1 ? words[words.length - 1]?.[0] : "";
  return `${first}${second}`.toUpperCase();
}

// Nhận diện lỗi backend báo phiên Zalo hết hạn (HTTP 401 + thông điệp/code).
function isSessionExpiredError(error: unknown): boolean {
  const msg = (error instanceof Error ? error.message : String(error || "")).toLowerCase();
  return (
    msg.includes("zca_session_expired") ||
    msg.includes("session_expired") ||
    msg.includes("hết hạn") ||
    msg.includes("đăng nhập lại") ||
    msg.includes("api 401")
  );
}

function conversationTimeMs(conversation: ZaloConversationSummary) {
  const value = conversation.latest_message_at;
  if (!value) return 0;
  const num = Number(value);
  if (!Number.isNaN(num) && String(num) === String(value).trim()) {
    return num < 1e11 ? num * 1000 : num;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

// Sắp xếp sidebar giống Zalo: pinned trước -> last_message_at DESC.
// unread_count CHỈ dùng để hiển thị badge, không tham gia thứ tự.
function sortConversationsLikeZalo(list: ZaloConversationSummary[]) {
  return [...list].sort((a, b) => {
    const pinA = a.is_pinned ? 1 : 0;
    const pinB = b.is_pinned ? 1 : 0;
    if (pinA !== pinB) return pinB - pinA;

    const tA = conversationTimeMs(a);
    const tB = conversationTimeMs(b);
    if (tA !== tB) return tB - tA;

    return (a.conversation_name || "").localeCompare(b.conversation_name || "");
  });
}

function messageKey(message: ZaloLibraryMessage) {
  return message.id || message.source_message_id || `${message.group_id}-${message.timestamp_text}-${message.content}`;
}

function isNearBottom(element: HTMLDivElement | null) {
  if (!element) return true;
  return element.scrollHeight - element.scrollTop - element.clientHeight <= BOTTOM_THRESHOLD_PX;
}

function messageAssets(message: ZaloLibraryMessage) {
  const list = (message.assets || []).filter((asset) => asset.status === "uploaded" && asset.storage_url);
  const seen = new Set<string>();
  const deduped: typeof list = [];
  for (const asset of list) {
    const src = asset.source_url || "";
    const filename = src.split("/").pop()?.split("?")[0] || src;
    if (filename && seen.has(filename)) {
      continue;
    }
    if (filename) {
      seen.add(filename);
    }
    deduped.push(asset);
  }
  return deduped;
}

interface SelectedMedia {
  file: File;
  previewUrl?: string;
}

const EMOJI_CATEGORIES = [
  {
    name: "Cảm xúc",
    emojis: ["😊", "😂", "🥰", "😍", "😉", "😘", "😜", "😎", "🤩", "🥳", "😀", "😃", "😄", "😁", "😆", "😅", "🤣", "😇", "🙂", "🙃", "😌", "😋", "😛", "😝", "😜", "🤪", "😏", "😒", "😞", "😔", "😟", "😕", "🙁", "☹️", "😣", "😖", "😫", "😩", "🥺", "😢", "😭", "😤", "😠", "😡", "🤬", "🤯", "😳", "🥵", "🥶", "😱", "😨", "😰", "😥", "😓", "🤔", "🤭", "🤫", "🤥", "😬", "🙄"]
  },
  {
    name: "Cử chỉ",
    emojis: ["👍", "👎", "👌", "✌️", "🤞", "🤟", "🤘", "🤙", "👈", "👉", "👆", "🖕", "👇", "☝️", "✊", "👊", "🤛", "🤜", "👏", "🙌", "👐", "🤲", "🤝", "🙏", "👋", "🤚", "🖐️", "✋", "🖖", "✍️", "💅", "🤳", "💪"]
  },
  {
    name: "Yêu thích",
    emojis: ["❤️", "💖", "💘", "💝", "💕", "💞", "💓", "💗", "❣️", "💟", "💌", "💔", "❤️‍🔥", "❤️‍🩹", "🔥", "✨", "⭐", "🌟", "💫", "💥", "💯", "🎉", "🎁", "🎈", "🍻", "☕", "🍕", "🧁", "🍓", "🐱", "🐶", "🌸", "🍀"]
  }
];

export function ZaloChatView({ flow, onBackToDashboard }: ZaloChatViewProps) {
  const [conversations, setConversations] = useState<ZaloConversationSummary[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ZaloLibraryMessage[]>([]);
  const [messageTotal, setMessageTotal] = useState(0);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const [newMessageCount, setNewMessageCount] = useState(0);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isLoadingOlderMessages, setIsLoadingOlderMessages] = useState(false);
  const [isSyncingRecent, setIsSyncingRecent] = useState(false);
  const [conversationError, setConversationError] = useState<string | null>(null);
  const [messageError, setMessageError] = useState<string | null>(null);
  const [syncSummary, setSyncSummary] = useState<ZaloSyncRecentResponse | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  // Chat UI states
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState<"all" | "unread" | "inactive">("all");
  const [inputText, setInputText] = useState("");
  const [avatarErrors, setAvatarErrors] = useState<Record<string, boolean>>({});
  
  // Auto send / Broadcast states
  const [selectedMessageIds, setSelectedMessageIds] = useState<string[]>([]);
  const [autoSendTargetIds, setAutoSendTargetIds] = useState<string[]>([]);
  const [autoSendSearchQuery, setAutoSendSearchQuery] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [autoSendSuccess, setAutoSendSuccess] = useState<string | null>(null);
  const [autoSendError, setAutoSendError] = useState<string | null>(null);

  // Direct send state
  const [isSendingDirect, setIsSendingDirect] = useState(false);
  const [directSendError, setDirectSendError] = useState<string | null>(null);

  // New media send and emoji states
  const [selectedMedia, setSelectedMedia] = useState<SelectedMedia[]>([]);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [activeEmojiTab, setActiveEmojiTab] = useState(0);

  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const emojiPickerRef = useRef<HTMLDivElement | null>(null);

  const messageListRef = useRef<HTMLDivElement | null>(null);
  const pendingScrollRef = useRef<"bottom" | "preserve" | null>(null);
  const preservedScrollRef = useRef<{ previousHeight: number; previousTop: number }>({ previousHeight: 0, previousTop: 0 });

  // Click outside listener for emoji picker
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (emojiPickerRef.current && !emojiPickerRef.current.contains(event.target as Node)) {
        setShowEmojiPicker(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const selectedAccount = useMemo(
    () => flow.accounts.find((account) => account.account_id === flow.userId) ?? null,
    [flow.accounts, flow.userId],
  );
  
  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.conversation_id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );

  const filteredConversations = useMemo(() => {
    let filtered = conversations;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(c => 
        (c.conversation_name || "").toLowerCase().includes(q) || 
        (c.latest_content || "").toLowerCase().includes(q)
      );
    }
    
    if (activeTab === "unread") {
      filtered = filtered.filter(c => 
        (c.unread_count !== undefined && c.unread_count > 0) ||
        (c.unread_count === undefined && c.message_count > 0 && c.latest_sender_name !== "Bạn")
      );
    } else if (activeTab === "inactive") {
      filtered = filtered.filter(c => 
        c.message_count === 0 || c.has_messages === false || c.sync_status === "known_empty"
      );
    }
    return filtered;
  }, [conversations, searchQuery, activeTab]);

  const loadConversations = useCallback(async (options?: { silent?: boolean }) => {
    if (!flow.userId || flow.userId === "default") {
      setConversations([]);
      setSelectedConversationId(null);
      return;
    }
    if (!options?.silent) setIsLoadingConversations(true);
    setConversationError(null);
    try {
      const response = await getZaloConversations(flow.userId);
      const nextConversations = sortConversationsLikeZalo(response.conversations ?? []);
      setConversations(nextConversations);
      setSelectedConversationId((current) => {
        if (current && nextConversations.some((item) => item.conversation_id === current)) {
          return current;
        }
        return nextConversations[0]?.conversation_id ?? null;
      });
    } catch (error) {
      setConversationError(error instanceof Error ? error.message : "Không thể tải danh sách hội thoại.");
    } finally {
      if (!options?.silent) setIsLoadingConversations(false);
    }
  }, [flow.userId]);

  const loadLatestMessages = useCallback(async (conversationId: string | null, options?: { silent?: boolean }) => {
    if (!flow.userId || flow.userId === "default" || !conversationId) {
      setMessages([]);
      setMessageTotal(0);
      setHasOlderMessages(false);
      return;
    }
    if (!options?.silent) setIsLoadingMessages(true);
    setMessageError(null);
    try {
      const response = await getZaloConversationMessages(
        flow.userId,
        conversationId,
        MESSAGE_PAGE_SIZE,
        0,
      );
      pendingScrollRef.current = "bottom";
      setMessages(response.messages ?? []);
      setMessageTotal(response.total ?? 0);
      setHasOlderMessages(Boolean(response.has_more));
      setNewMessageCount(0);
    } catch (error) {
      setMessageError(error instanceof Error ? error.message : "Không thể tải tin nhắn hội thoại.");
    } finally {
      if (!options?.silent) setIsLoadingMessages(false);
    }
  }, [flow.userId]);

  const pollLatestMessages = useCallback(async (conversationId: string | null) => {
    if (!flow.userId || flow.userId === "default" || !conversationId) return;
    const shouldStickToBottom = isNearBottom(messageListRef.current);
    try {
      const response = await getZaloConversationMessages(
        flow.userId,
        conversationId,
        MESSAGE_PAGE_SIZE,
        0,
      );
      const latestMessages = response.messages ?? [];
      setMessageTotal(response.total ?? 0);
      setHasOlderMessages((response.total ?? 0) > messages.length);
      setMessages((current) => {
        const latestMap = new Map(latestMessages.map(m => [messageKey(m), m]));
        
        // Update existing messages, and track which ones from latestMessages we have seen
        const updated = current.map(m => {
          const key = messageKey(m);
          if (latestMap.has(key)) {
            return latestMap.get(key)!;
          }
          return m;
        });
        
        // Find messages in latestMessages that are not in current
        const existingKeys = new Set(current.map(messageKey));
        const newMessages = latestMessages.filter(m => !existingKeys.has(messageKey(m)));
        
        if (newMessages.length === 0) {
          const hasChanges = current.some((m, idx) => {
            const key = messageKey(m);
            if (!latestMap.has(key)) return false;
            const next = latestMap.get(key)!;
            return JSON.stringify(m) !== JSON.stringify(next);
          });
          return hasChanges ? updated : current;
        }
        
        if (!shouldStickToBottom) setNewMessageCount((count) => count + newMessages.length);
        if (shouldStickToBottom) pendingScrollRef.current = "bottom";
        
        return [...updated, ...newMessages];
      });
    } catch {
      // Silent polling should not interrupt the operator while they are reading.
    }
  }, [flow.userId, messages.length]);

  const loadOlderMessages = useCallback(async () => {
    if (!flow.userId || !selectedConversationId || isLoadingOlderMessages || !hasOlderMessages) return;
    const element = messageListRef.current;
    const previousHeight = element?.scrollHeight ?? 0;
    const previousTop = element?.scrollTop ?? 0;
    setIsLoadingOlderMessages(true);
    setMessageError(null);
    try {
      const response = await getZaloConversationMessages(
        flow.userId,
        selectedConversationId,
        MESSAGE_PAGE_SIZE,
        messages.length,
      );
      const olderMessages = response.messages ?? [];
      preservedScrollRef.current = { previousHeight, previousTop };
      pendingScrollRef.current = "preserve";
      setMessages((current) => {
        const existing = new Set(current.map(messageKey));
        const uniqueOlder = olderMessages.filter((message) => !existing.has(messageKey(message)));
        return [...uniqueOlder, ...current];
      });
      setMessageTotal(response.total ?? messageTotal);
      setHasOlderMessages(messages.length + olderMessages.length < (response.total ?? 0));
    } catch (error) {
      setMessageError(error instanceof Error ? error.message : "Không thể tải tin nhắn cũ hơn.");
    } finally {
      setIsLoadingOlderMessages(false);
    }
  }, [flow.userId, hasOlderMessages, isLoadingOlderMessages, messageTotal, messages.length, selectedConversationId]);

  const scrollToLatest = useCallback(() => {
    const element = messageListRef.current;
    if (element) element.scrollTop = element.scrollHeight;
    setNewMessageCount(0);
  }, []);

  const syncRecentConversations = useCallback(async () => {
    if (!flow.userId || flow.userId === "default" || isSyncingRecent) return;
    setIsSyncingRecent(true);
    setSyncSummary(null);
    setSyncError(null);
    try {
      const response = await syncZaloRecentConversations(
        flow.userId,
        SYNC_CONVERSATION_LIMIT,
        SYNC_MESSAGES_PER_CONVERSATION,
      );
      setSyncSummary(response);
      if (response.errors > 0 && response.messages_saved === 0) {
        setSyncError(
          `Đồng bộ xong nhưng không lấy được tin nhắn (quét ${response.scanned} nhóm, lỗi ${response.errors}). Listener Zalo có thể chưa kết nối — thử lại sau vài giây.`,
        );
      }
      await loadConversations();
      if (selectedConversationId) await loadLatestMessages(selectedConversationId, { silent: true });
    } catch (error) {
      if (isSessionExpiredError(error)) {
        setSyncError("Phiên đăng nhập Zalo đã hết hạn. Vui lòng đăng nhập lại bằng mã QR.");
        void flow.refreshLoginStatus();
      } else {
        setSyncError(error instanceof Error ? error.message : "Không thể đồng bộ tin nhắn.");
      }
    } finally {
      setIsSyncingRecent(false);
    }
  }, [flow, isSyncingRecent, loadConversations, loadLatestMessages, selectedConversationId]);

  useEffect(() => {
    const action = pendingScrollRef.current;
    if (!action) return;
    pendingScrollRef.current = null;
    const element = messageListRef.current;
    if (!element) return;
    if (action === "bottom") {
      element.scrollTop = element.scrollHeight;
    } else if (action === "preserve") {
      const { previousHeight, previousTop } = preservedScrollRef.current;
      element.scrollTop = element.scrollHeight - previousHeight + previousTop;
    }
  }, [messages]);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    setMessages([]);
    setMessageTotal(0);
    setHasOlderMessages(false);
    setNewMessageCount(0);
    setSelectedMessageIds([]); // Reset selection when switching conversations
    void loadLatestMessages(selectedConversationId);

    if (selectedConversationId && flow.userId && flow.userId !== "default") {
      void markZaloConversationAsRead(flow.userId, selectedConversationId)
        .then(() => {
          setConversations((prev) =>
            prev.map((c) =>
              c.conversation_id === selectedConversationId
                ? { ...c, unread_count: 0 }
                : c
            )
          );
        })
        .catch((err) => {
          console.error("Failed to mark conversation as read:", err);
        });
    }
  }, [loadLatestMessages, selectedConversationId, flow.userId]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadConversations({ silent: true });
      void pollLatestMessages(selectedConversationId);
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loadConversations, pollLatestMessages, selectedConversationId]);

  const handleToggleSelectMessage = (messageId: string) => {
    setSelectedMessageIds(prev => 
      prev.includes(messageId) 
        ? prev.filter(id => id !== messageId)
        : [...prev, messageId]
    );
  };

  const autoSendFilteredConversations = useMemo(() => {
    if (!autoSendSearchQuery) return conversations;
    const q = autoSendSearchQuery.toLowerCase();
    return conversations.filter(c =>
      (c.conversation_name || "").toLowerCase().includes(q) ||
      (c.latest_content || "").toLowerCase().includes(q)
    );
  }, [conversations, autoSendSearchQuery]);

  const handleToggleAutoSendTarget = (conversationId: string) => {
    setAutoSendTargetIds(prev =>
      prev.includes(conversationId)
        ? prev.filter(id => id !== conversationId)
        : [...prev, conversationId]
    );
  };

  const handleAutoSend = async () => {
    if (!flow.userId || selectedMessageIds.length === 0 || autoSendTargetIds.length === 0) return;
    setIsSending(true);
    setAutoSendError(null);
    setAutoSendSuccess(null);

    const targets: ZaloBroadcastTarget[] = autoSendTargetIds
      .map((id): ZaloBroadcastTarget | null => {
        const conv = conversations.find(c => c.conversation_id === id);
        if (!conv) return null;
        const name = isFallbackName(conv.conversation_name, conv.conversation_id)
          ? conv.conversation_id
          : (conv.conversation_name || conv.conversation_id);
        return { group_id: conv.conversation_id, group_name: name };
      })
      .filter((t): t is ZaloBroadcastTarget => t !== null);

    if (targets.length === 0) {
      setAutoSendError("Không tìm thấy người nhận hợp lệ.");
      setIsSending(false);
      return;
    }

    try {
      await createZaloBroadcast(flow.userId, {
        user_id: flow.userId,
        message_ids: selectedMessageIds,
        targets,
        content_mode: "both",
      });
      setAutoSendSuccess(`Đã lên lịch gửi đến ${targets.length} người nhận thành công!`);
      setAutoSendTargetIds([]);
      setSelectedMessageIds([]);
    } catch (err) {
      setAutoSendError(err instanceof Error ? err.message : "Lỗi gửi tin.");
    } finally {
      setIsSending(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newMedia = Array.from(e.target.files).map((file) => {
        const isImage = file.type.startsWith("image/");
        return {
          file,
          previewUrl: isImage ? URL.createObjectURL(file) : undefined,
        };
      });
      setSelectedMedia((prev) => [...prev, ...newMedia]);
    }
    e.target.value = "";
  };

  const handleRemoveMedia = (index: number) => {
    setSelectedMedia((prev) => {
      const item = prev[index];
      if (item && item.previewUrl) {
        URL.revokeObjectURL(item.previewUrl);
      }
      return prev.filter((_, i) => i !== index);
    });
  };

  const handleEmojiClick = (emoji: string) => {
    setInputText((prev) => prev + emoji);
  };

  const handleSingleSend = async () => {
    if (!selectedConversation || isSendingDirect) return;
    const textToSend = inputText.trim();
    if (!textToSend && selectedMedia.length === 0) return;

    setInputText("");
    const mediaToSend = [...selectedMedia];
    setSelectedMedia([]);
    setDirectSendError(null);
    setIsSendingDirect(true);

    try {
      if (mediaToSend.length > 0) {
        const filesOnly = mediaToSend.map((m) => m.file);
        await sendZaloMessageWithFiles(
          flow.userId,
          selectedConversation.conversation_id,
          textToSend,
          filesOnly
        );
      } else {
        await sendZaloMessage(flow.userId, selectedConversation.conversation_id, {
          text: textToSend,
        });
      }
      mediaToSend.forEach((m) => {
        if (m.previewUrl) URL.revokeObjectURL(m.previewUrl);
      });
      await loadLatestMessages(selectedConversationId, { silent: true });
    } catch (err) {
      setDirectSendError(err instanceof Error ? err.message : "Không thể gửi tin nhắn.");
      setInputText(textToSend);
      setSelectedMedia(mediaToSend);
    } finally {
      setIsSendingDirect(false);
    }
  };

  return (
    <div className="flex h-[85vh] overflow-hidden rounded-2xl border border-outline-variant bg-surface-container-lowest shadow-sm">

      {/* Left Column: Conversations */}
      <div className="flex w-[320px] flex-col border-r border-outline-variant bg-surface">
        {flow.sessionExpired && (
          <div className="m-sm rounded-lg border border-error-container bg-error-container/40 px-sm py-xs text-xs text-error">
            <div className="font-semibold flex items-center gap-xs">
              <MaterialIcon name="error" className="text-sm" />
              Phiên Zalo đã hết hạn
            </div>
            <p className="mt-0.5">Tin nhắn sẽ không tự cập nhật. Hãy đăng nhập lại bằng mã QR để tiếp tục.</p>
            <button
              onClick={onBackToDashboard}
              className="mt-xs w-full rounded-md bg-error px-sm py-1 font-semibold text-on-error hover:opacity-90 transition"
            >
              Đăng nhập lại
            </button>
          </div>
        )}
        <div className="p-md border-b border-outline-variant">
          <div className="flex items-center gap-sm mb-md">
            <button 
              onClick={onBackToDashboard}
              className="text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low p-1 rounded-full transition"
            >
              <MaterialIcon name="arrow_back" className="text-xl" />
            </button>
            <div className="min-w-0">
              <div className="font-semibold truncate">{selectedAccount?.label || "Đang chat"}</div>
              <div className="text-xs text-on-surface-variant truncate">UID: {shortId(flow.userId)}</div>
            </div>
            {flow.isLoggedIn && (
              <button 
                onClick={() => void flow.endSession()}
                className="ml-auto text-xs text-red-600 hover:bg-red-50 px-2 py-1 rounded-md border border-red-200 transition"
                title="Đăng xuất khỏi Zalo"
              >
                Đăng xuất
              </button>
            )}
          </div>
          
          <div className="relative mb-md">
            <MaterialIcon name="search" className="absolute left-sm top-1/2 -translate-y-1/2 text-on-surface-variant text-sm" />
            <input
              type="text"
              placeholder="Tìm kiếm..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-full border border-outline-variant bg-surface-container-low py-1.5 pl-8 pr-md text-body-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/50"
            />
          </div>

          <div className="flex gap-xs">
            <button 
              onClick={() => setActiveTab('all')}
              className={`flex-1 pb-1 text-center text-xs font-semibold border-b-2 transition ${activeTab === 'all' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-on-surface'}`}
            >
              Tất cả
            </button>
            <button 
              onClick={() => setActiveTab('unread')}
              className={`flex-1 pb-1 text-center text-xs font-semibold border-b-2 transition ${activeTab === 'unread' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-on-surface'}`}
            >
              Chưa đọc
            </button>
            <button 
              onClick={() => setActiveTab('inactive')}
              className={`flex-1 pb-1 text-center text-xs font-semibold border-b-2 transition ${activeTab === 'inactive' ? 'border-primary text-primary' : 'border-transparent text-on-surface-variant hover:text-on-surface'}`}
            >
              Chưa hoạt động
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoadingConversations && conversations.length === 0 && (
            <div className="p-xl text-center text-on-surface-variant text-sm">
              Đang tải hội thoại...
            </div>
          )}
          {conversationError && (
            <div className="mx-md mt-md text-xs text-error bg-error-container/40 p-sm rounded-lg">
              {conversationError}
            </div>
          )}
          {filteredConversations.map((conversation) => {
            const active = conversation.conversation_id === selectedConversationId;
            const title = conversationTitle(conversation);
            return (
              <button
                key={conversation.conversation_id}
                onClick={() => setSelectedConversationId(conversation.conversation_id)}
                className={`w-full flex items-start gap-md p-md text-left transition border-b border-outline-variant/50 hover:bg-surface-container-low ${
                  active ? "bg-primary/10" : ""
                }`}
              >
                {conversation.avatar_url && !avatarErrors[conversation.conversation_id] ? (
                  <img
                    src={conversation.avatar_url}
                    alt={title}
                    onError={() => setAvatarErrors(prev => ({ ...prev, [conversation.conversation_id]: true }))}
                    className="h-12 w-12 shrink-0 rounded-full object-cover border border-outline-variant/30 bg-surface-container-low"
                  />
                ) : (
                  <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-title-md font-semibold ${
                    active ? "bg-primary text-on-primary" : "bg-primary-container text-on-primary-container"
                  }`}>
                    {initials(title)}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between mb-0.5">
                    <div className={`font-semibold truncate text-on-surface ${conversation.unread_count && conversation.unread_count > 0 ? "font-bold" : ""}`}>{title}</div>
                    <div className="text-xs text-on-surface-variant shrink-0">{formatTime(conversation.latest_message_at)}</div>
                  </div>
                  <div className="flex items-center justify-between gap-xs">
                    <div className={`text-sm truncate flex-1 ${conversation.unread_count && conversation.unread_count > 0 ? 'text-on-surface font-semibold' : active ? 'text-on-surface font-medium' : 'text-on-surface-variant'}`}>
                      {conversation.latest_sender_name ? `${conversation.latest_sender_name}: ` : ""}{conversation.latest_content || "Tin nhắn mới"}
                    </div>
                    {conversation.unread_count !== undefined && conversation.unread_count > 0 && (
                      <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white shadow-sm">
                        {conversation.unread_count}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
          {filteredConversations.length === 0 && !isLoadingConversations && (
            <div className="p-xl text-center text-on-surface-variant text-sm">
              {searchQuery ? "Không tìm thấy hội thoại phù hợp" : "Chưa có hội thoại. Bấm Đồng bộ để tải về."}
            </div>
          )}
        </div>
        
        <div className="p-sm border-t border-outline-variant bg-surface-container-lowest">
           <button
             onClick={() => void syncRecentConversations()}
             disabled={isSyncingRecent}
             className="w-full flex items-center justify-center gap-xs py-2 text-sm font-semibold text-primary hover:bg-primary/10 rounded-lg transition"
           >
             <MaterialIcon name="sync" className={`text-base ${isSyncingRecent ? 'animate-spin' : ''}`} />
             Đồng bộ tin nhắn mới
           </button>
           {syncError && (
             <div className="mt-xs rounded-lg border border-error-container bg-error-container/40 px-sm py-xs text-xs text-error">
               {syncError}
             </div>
           )}
           {!syncError && syncSummary && (
             <div className="mt-xs rounded-lg border border-outline-variant bg-surface-container-low px-sm py-xs text-xs text-on-surface-variant">
               Đã quét {syncSummary.scanned} nhóm · lưu {syncSummary.messages_saved} tin · {syncSummary.groups_with_messages} nhóm có tin mới
             </div>
           )}
        </div>
      </div>

      {/* Middle Column: Chat */}
      <div className="flex flex-1 flex-col bg-[#eef0f2]">
        {!flow.isLoggedIn ? (
          <div className="flex-1 flex flex-col items-center justify-center p-xl w-full">
            {/* QR Code Display - 3 states: has QR, generating QR, no QR */}
            {flow.qrBase64 ? (
              <>
                <div className="bg-white p-lg rounded-2xl shadow-lg mb-md border-2 border-primary/20 relative">
                  <img
                    src={flow.qrBase64.startsWith("data:") ? flow.qrBase64 : `data:image/png;base64,${flow.qrBase64}`}
                    alt="Zalo QR"
                    className="w-56 h-56 object-contain"
                  />
                  {flow.authStatus === "waiting_scan" && (
                    <div className="absolute -bottom-3 left-1/2 -translate-x-1/2 bg-primary text-on-primary px-md py-1 rounded-full text-xs font-semibold shadow-md animate-pulse whitespace-nowrap">
                      Đang chờ quét mã...
                    </div>
                  )}
                </div>
                <h3 className="text-title-md font-semibold mb-xs text-center mt-sm">Quét mã QR bằng Zalo</h3>
                <p className="text-body-sm text-on-surface-variant mb-md text-center max-w-xs">
                  Mở ứng dụng Zalo trên điện thoại → Quét QR → Xác nhận đăng nhập
                </p>
                <div className="flex gap-sm">
                  <button
                    onClick={() => void flow.startSession()}
                    disabled={flow.isStartingSession}
                    className="border border-outline-variant bg-surface text-on-surface px-lg py-sm rounded-lg text-sm font-semibold hover:bg-surface-container-low transition disabled:opacity-50"
                  >
                    {flow.isStartingSession ? "Đang tạo..." : "Làm mới QR"}
                  </button>
                </div>
              </>
            ) : flow.isStartingSession ? (
              <>
                <div className="w-56 h-56 bg-surface-container-low rounded-2xl mb-lg flex items-center justify-center border-2 border-dashed border-outline-variant">
                  <div className="flex flex-col items-center gap-sm text-on-surface-variant">
                    <MaterialIcon name="qr_code_scanner" className="text-5xl animate-pulse text-primary" />
                    <span className="text-sm font-medium">Đang tạo mã QR...</span>
                  </div>
                </div>
                <p className="text-body-sm text-on-surface-variant text-center max-w-xs">
                  Hệ thống đang khởi tạo phiên Zalo và tạo mã QR. Quá trình này có thể mất vài giây.
                </p>
              </>
            ) : (
              <>
                <MaterialIcon name="qr_code_scanner" className="text-6xl mb-md text-primary opacity-60" />
                <h3 className="text-title-lg font-semibold mb-sm text-center">Tài khoản chưa đăng nhập</h3>
                <p className="text-body-md text-on-surface-variant mb-lg text-center w-full max-w-md">
                  Bạn cần kết nối tài khoản Zalo này qua mã QR để hệ thống có thể đọc tin nhắn và thực hiện Auto Send.
                </p>
                <button
                  onClick={() => void flow.startSession()}
                  disabled={flow.isStartingSession}
                  className="bg-primary text-on-primary px-xl py-sm rounded-lg font-semibold shadow-sm hover:bg-primary/90 transition disabled:opacity-50"
                >
                  Tạo mã QR Đăng Nhập
                </button>
              </>
            )}
            {flow.authStatus === "qr_expired" && (
              <div className="mt-md text-sm text-orange-600 bg-orange-50 px-md py-2 rounded-lg border border-orange-100">
                Mã QR đã hết hạn. Bấm &quot;Làm mới QR&quot; để tạo mã mới.
              </div>
            )}
          </div>
        ) : selectedConversation ? (
          <>
            {/* Chat Header */}
            <header className="flex items-center justify-between border-b border-outline-variant bg-surface p-md shadow-sm z-10">
              <div className="flex items-center gap-md">
                {selectedConversation.avatar_url && !avatarErrors[`header-${selectedConversation.conversation_id}`] ? (
                  <img
                    src={selectedConversation.avatar_url}
                    alt={conversationTitle(selectedConversation)}
                    onError={() => setAvatarErrors(prev => ({ ...prev, [`header-${selectedConversation.conversation_id}`]: true }))}
                    className="h-10 w-10 shrink-0 rounded-full object-cover border border-outline-variant/30 bg-surface-container-low"
                  />
                ) : (
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-on-primary font-bold">
                    {initials(conversationTitle(selectedConversation))}
                  </div>
                )}
                <div>
                  <h3 className="font-semibold text-title-md text-on-surface">{conversationTitle(selectedConversation)}</h3>
                  <div className="flex items-center gap-xs text-xs text-on-surface-variant mt-0.5">
                    <span className="w-2 h-2 rounded-full bg-green-500"></span>
                    Trực tuyến
                  </div>
                </div>
              </div>
              <div className="flex gap-sm">
                <button className="h-9 w-9 flex items-center justify-center rounded-full hover:bg-surface-container-low text-on-surface-variant transition">
                  <MaterialIcon name="search" />
                </button>
                <button className="h-9 w-9 flex items-center justify-center rounded-full hover:bg-surface-container-low text-on-surface-variant transition">
                  <MaterialIcon name="call" />
                </button>
                <button className="h-9 w-9 flex items-center justify-center rounded-full hover:bg-surface-container-low text-on-surface-variant transition">
                  <MaterialIcon name="videocam" />
                </button>
              </div>
            </header>

            {/* Messages Area */}
            <div ref={messageListRef} className="flex-1 overflow-y-auto p-md space-y-md">
              {hasOlderMessages && (
                <div className="flex justify-center mb-md">
                  <button
                    onClick={() => void loadOlderMessages()}
                    disabled={isLoadingOlderMessages}
                    className="bg-surface border border-outline-variant text-on-surface-variant hover:bg-surface-container-low rounded-full px-lg py-1.5 text-sm font-semibold shadow-sm transition"
                  >
                    {isLoadingOlderMessages ? "Đang tải..." : "Tải thêm tin cũ"}
                  </button>
                </div>
              )}

              {messages.map((message) => {
                const assets = messageAssets(message);
                const sender = message.sender_name || (message.is_sent ? "Bạn" : "Khách");
                const isSentByMe = message.is_sent;
                const msgId = messageKey(message);
                const isSelected = selectedMessageIds.includes(msgId);

                return (
                  <div key={msgId} className={`flex group ${isSentByMe ? 'justify-end' : 'justify-start'}`}>
                    {/* Checkbox for Auto Send Selection - visible on hover or if selected */}
                    {!isSentByMe && (
                       <div className={`mr-2 pt-2 transition-opacity ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                         <input 
                           type="checkbox" 
                           className="w-4 h-4 cursor-pointer"
                           checked={isSelected}
                           onChange={() => handleToggleSelectMessage(msgId)}
                         />
                       </div>
                    )}

                    <div className={`max-w-[75%] rounded-2xl px-lg py-sm shadow-sm relative ${
                      isSentByMe 
                        ? 'bg-[#e5efff] text-on-surface rounded-br-none' 
                        : 'bg-white text-on-surface rounded-bl-none border border-outline-variant/30'
                    } ${isSelected ? 'ring-2 ring-primary ring-offset-2' : ''}`}>
                      
                      {!isSentByMe && (
                        <div className="text-xs font-semibold mb-1 opacity-70">
                          {sender}
                        </div>
                      )}
                      
                      {message.content && (
                        <p className="whitespace-pre-wrap break-words text-body-md leading-relaxed">
                          {message.content}
                        </p>
                      )}
                      
                      {assets.length > 0 && (
                        <div className="mt-sm grid gap-xs sm:grid-cols-2">
                          {assets.map((asset) => (
                            <Image
                              key={asset.id || asset.storage_url}
                              src={asset.storage_url || ""}
                              alt="Image"
                              width={260}
                              height={180}
                              className="rounded-lg object-cover w-full h-auto"
                              unoptimized
                            />
                          ))}
                        </div>
                      )}

                      <div className={`text-[11px] mt-1 text-right ${isSentByMe ? 'text-primary/70' : 'text-on-surface-variant'}`}>
                        {formatTime(message.timestamp_text || message.time_text)}
                      </div>
                    </div>

                    {isSentByMe && (
                       <div className={`ml-2 pt-2 transition-opacity ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                         <input 
                           type="checkbox" 
                           className="w-4 h-4 cursor-pointer"
                           checked={isSelected}
                           onChange={() => handleToggleSelectMessage(msgId)}
                         />
                       </div>
                    )}
                  </div>
                );
              })}

              {newMessageCount > 0 && (
                <div className="sticky bottom-md flex justify-center z-10">
                  <button
                    onClick={scrollToLatest}
                    className="bg-primary text-on-primary rounded-full px-lg py-1.5 text-sm font-semibold shadow-md flex items-center gap-xs hover:bg-primary/90 transition"
                  >
                    <MaterialIcon name="arrow_downward" className="text-sm" />
                    Có {newMessageCount} tin mới
                  </button>
                </div>
              )}
            </div>

            {/* Quick Replies */}
            <div className="px-md pb-xs pt-sm flex gap-sm overflow-x-auto whitespace-nowrap bg-[#eef0f2]">
               <button className="bg-surface border border-outline-variant rounded-full px-md py-1.5 text-xs font-semibold text-on-surface hover:bg-surface-container-low">
                 Dạ vâng, chị nhắn địa chỉ chi tiết giúp em nhé.
               </button>
               <button className="bg-surface border border-outline-variant rounded-full px-md py-1.5 text-xs font-semibold text-on-surface hover:bg-surface-container-low">
                 Ok ạ, em đang sẵn sàng ghi nhận đấy ạ.
               </button>
            </div>

            {/* Chat Input */}
            <div className="bg-surface p-md border-t border-outline-variant relative">
              {/* Invisible Inputs */}
              <input
                type="file"
                ref={imageInputRef}
                multiple
                accept="image/*"
                onChange={handleFileChange}
                className="hidden"
              />
              <input
                type="file"
                ref={fileInputRef}
                multiple
                accept="*/*"
                onChange={handleFileChange}
                className="hidden"
              />

              {/* Emoji Picker Popup */}
              {showEmojiPicker && (
                <div
                  ref={emojiPickerRef}
                  className="absolute bottom-full mb-3 left-4 z-50 w-72 h-80 bg-surface border border-outline-variant rounded-2xl shadow-xl flex flex-col overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200"
                  style={{ maxHeight: '320px' }}
                >
                  {/* Category selector */}
                  <div className="flex border-b border-outline-variant bg-surface-container-low px-sm py-1">
                    {EMOJI_CATEGORIES.map((cat, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => setActiveEmojiTab(i)}
                        className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition ${
                          activeEmojiTab === i
                            ? "bg-surface text-primary shadow-sm"
                            : "text-on-surface-variant hover:text-on-surface"
                        }`}
                      >
                        {cat.name}
                      </button>
                    ))}
                  </div>

                  {/* Emoji grid */}
                  <div className="flex-1 overflow-y-auto p-sm grid grid-cols-6 gap-xs content-start">
                    {EMOJI_CATEGORIES[activeEmojiTab].emojis.map((emoji, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => handleEmojiClick(emoji)}
                        className="h-9 w-9 flex items-center justify-center text-xl rounded-lg hover:bg-surface-container-high active:scale-95 transition"
                      >
                        {emoji}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Direct Send Error */}
              {directSendError && (
                <div className="mb-sm text-xs text-error bg-error-container/40 px-sm py-1.5 rounded-lg">
                  {directSendError}
                </div>
              )}

              {/* Selected Media Previews */}
              {selectedMedia.length > 0 && (
                <div className="flex flex-wrap gap-sm p-sm mb-md rounded-xl border border-outline-variant/60 bg-surface-container-lowest max-h-32 overflow-y-auto">
                  {selectedMedia.map((item, index) => {
                    const isImage = !!item.previewUrl;
                    return (
                      <div
                        key={index}
                        className="relative group w-14 h-14 rounded-lg border border-outline-variant bg-surface overflow-hidden flex items-center justify-center shadow-sm hover:border-primary/50 transition"
                      >
                        {isImage ? (
                          <img
                            src={item.previewUrl}
                            alt={item.file.name}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <div className="flex flex-col items-center justify-center p-1 text-center w-full h-full">
                            <MaterialIcon name="description" className="text-xl text-primary" />
                            <span className="text-[9px] truncate w-full px-1 mt-0.5 text-on-surface-variant font-medium">
                              {item.file.name}
                            </span>
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => handleRemoveMedia(index)}
                          className="absolute -top-1 -right-1 bg-red-500 hover:bg-red-600 text-white rounded-full p-0.5 shadow-md transition transform scale-0 group-hover:scale-100 flex items-center justify-center"
                          style={{ width: '16px', height: '16px' }}
                        >
                          <MaterialIcon name="close" className="text-[10px] font-bold" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="flex items-center gap-sm">
                <button
                  type="button"
                  onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                  className={`text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-surface-container-low transition ${
                    showEmojiPicker ? "text-primary bg-primary/10" : ""
                  }`}
                  title="Biểu cảm"
                >
                  <MaterialIcon name="mood" />
                </button>
                <button
                  type="button"
                  onClick={() => imageInputRef.current?.click()}
                  className="text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-surface-container-low transition"
                  title="Gửi hình ảnh"
                >
                  <MaterialIcon name="image" />
                </button>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="text-on-surface-variant hover:text-on-surface p-1 rounded-full hover:bg-surface-container-low transition"
                  title="Gửi file tài liệu"
                >
                  <MaterialIcon name="attach_file" />
                </button>

                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder={
                    selectedMedia.length > 0
                      ? "Nhập chữ kèm theo file (tùy chọn), Enter để gửi..."
                      : "Nhập tin nhắn, Enter để gửi..."
                  }
                  disabled={isSendingDirect}
                  className="flex-1 bg-surface-container-low rounded-xl px-md py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-60"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void handleSingleSend();
                    }
                  }}
                />

                <button
                  onClick={() => void handleSingleSend()}
                  disabled={isSendingDirect || (!inputText.trim() && selectedMedia.length === 0)}
                  className="bg-primary text-on-primary h-10 w-10 rounded-full flex items-center justify-center hover:bg-primary/90 transition shadow-sm disabled:opacity-50"
                >
                  {isSendingDirect ? (
                    <span className="text-xs">...</span>
                  ) : (
                    <MaterialIcon name="send" className="text-sm ml-1" />
                  )}
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center bg-[#eef0f2]">
            <div className="text-center text-on-surface-variant">
              <MaterialIcon name="chat" className="text-6xl mb-md opacity-20" />
              <p className="text-lg font-medium">Chọn một hội thoại để bắt đầu</p>
            </div>
          </div>
        )}
      </div>

      {/* Right Column: Auto Send */}
      <div className="w-[320px] flex flex-col bg-surface border-l border-outline-variant">
        <header className="border-b border-outline-variant p-md flex items-center justify-between">
          <div className="flex items-center gap-xs text-primary font-semibold">
            <MaterialIcon name="send" />
            Auto Send
          </div>
          <button className="text-on-surface-variant hover:text-on-surface">
             <MaterialIcon name="close" className="text-xl" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-md space-y-lg">
          <div className="bg-surface-container-lowest border border-primary/20 rounded-xl p-md">
            <h4 className="text-sm font-semibold mb-xs flex items-center gap-xs text-on-surface">
              <MaterialIcon name="auto_awesome" className="text-primary text-sm" />
              Gửi tin nhắn hàng loạt
            </h4>
            <p className="text-xs text-on-surface-variant leading-relaxed mb-md">
              Tích chọn tin nhắn ở khung chat bên trái làm nội dung mẫu, sau đó chọn người nhận bên dưới.
            </p>

            <div className="mb-md">
              <div className="text-xs font-semibold uppercase text-on-surface-variant mb-sm">Nội dung mẫu</div>
              {selectedMessageIds.length > 0 ? (
                <div className="bg-primary-container/30 text-on-primary-container px-sm py-xs rounded-lg text-xs font-medium inline-flex items-center gap-xs border border-primary/20">
                  <MaterialIcon name="check_circle" className="text-[14px]" />
                  Đã chọn {selectedMessageIds.length} tin nhắn
                </div>
              ) : (
                <div className="text-xs text-orange-600 bg-orange-50 px-sm py-2 rounded-lg border border-orange-100 italic">
                  Chưa chọn tin nhắn nào. Hãy tick vào checkbox bên cạnh tin nhắn.
                </div>
              )}
            </div>

            <div className="mb-md">
              <div className="text-xs font-semibold uppercase text-on-surface-variant mb-sm">
                Người nhận ({autoSendTargetIds.length} đã chọn)
              </div>

              {/* Search conversations for Auto Send */}
              <div className="relative mb-sm">
                <MaterialIcon name="search" className="absolute left-2 top-1/2 -translate-y-1/2 text-on-surface-variant text-sm" />
                <input
                  type="text"
                  placeholder="Tìm nhóm hoặc người nhận..."
                  value={autoSendSearchQuery}
                  onChange={(e) => setAutoSendSearchQuery(e.target.value)}
                  className="w-full text-xs border border-outline-variant rounded-lg py-1.5 pl-7 pr-sm bg-surface focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Selected target chips */}
              {autoSendTargetIds.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-sm">
                  {autoSendTargetIds.map(id => {
                    const conv = conversations.find(c => c.conversation_id === id);
                    const name = conv ? conversationTitle(conv) : id;
                    return (
                      <button
                        key={id}
                        type="button"
                        onClick={() => handleToggleAutoSendTarget(id)}
                        className="inline-flex items-center gap-0.5 rounded-full bg-primary-container text-on-primary-container px-2 py-0.5 text-[11px] font-semibold hover:bg-primary/20 transition"
                      >
                        {name.length > 18 ? `${name.slice(0, 18)}…` : name}
                        <MaterialIcon name="close" className="text-[12px]" />
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Conversation picker list */}
              <div className="max-h-48 overflow-y-auto border border-outline-variant rounded-lg bg-surface divide-y divide-outline-variant/50">
                {autoSendFilteredConversations.length > 0 ? (
                  autoSendFilteredConversations.map(conv => {
                    const title = conversationTitle(conv);
                    const checked = autoSendTargetIds.includes(conv.conversation_id);
                    const isCurrentConv = conv.conversation_id === selectedConversationId;
                    return (
                      <label
                        key={conv.conversation_id}
                        className={`flex items-center gap-sm px-sm py-1.5 cursor-pointer hover:bg-surface-container-low transition text-xs ${
                          checked ? 'bg-primary-container/20' : ''
                        } ${isCurrentConv ? 'border-l-2 border-l-primary' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => handleToggleAutoSendTarget(conv.conversation_id)}
                          className="w-3.5 h-3.5 shrink-0"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="font-semibold truncate text-on-surface">{title}</div>
                          {conv.latest_content && (
                            <div className="text-[11px] text-on-surface-variant truncate">{conv.latest_content}</div>
                          )}
                        </div>
                      </label>
                    );
                  })
                ) : (
                  <div className="px-sm py-lg text-center text-[11px] text-on-surface-variant">
                    {conversations.length === 0
                      ? "Chưa có hội thoại. Bấm Đồng bộ ở bên trái."
                      : "Không tìm thấy hội thoại phù hợp."}
                  </div>
                )}
              </div>
            </div>

            {autoSendError && (
              <div className="mb-md text-xs text-error bg-error-container/40 p-sm rounded-lg">
                {autoSendError}
              </div>
            )}

            {autoSendSuccess && (
              <div className="mb-md text-xs text-green-700 bg-green-50 border border-green-200 p-sm rounded-lg">
                {autoSendSuccess}
              </div>
            )}

            <button
              onClick={() => void handleAutoSend()}
              disabled={isSending || selectedMessageIds.length === 0 || autoSendTargetIds.length === 0}
              className="w-full bg-primary text-on-primary py-2 rounded-lg text-sm font-semibold flex items-center justify-center gap-xs hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <MaterialIcon name="send" className="text-sm" />
              {isSending ? "Đang gửi..." : autoSendTargetIds.length > 0 ? `Gửi đến ${autoSendTargetIds.length} người nhận` : "Thực hiện Auto Send"}
            </button>
          </div>
        </div>
      </div>
      
    </div>
  );
}
