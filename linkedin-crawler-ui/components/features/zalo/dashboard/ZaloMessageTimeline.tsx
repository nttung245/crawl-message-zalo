"use client";

import { MaterialIcon } from "@/components/ui";
import type { ZaloMessage } from "@/types/zalo-api";

interface ZaloMessageTimelineProps {
  messages: ZaloMessage[];
}

export function ZaloMessageTimeline({ messages }: ZaloMessageTimelineProps) {
  if (messages.length === 0) {
    return (
      <div className="border-outline-variant bg-surface rounded-xl border px-md py-lg text-body-sm text-on-surface-variant">
        Backend hiện mới trả về tiến độ tổng hợp cho job. Timeline đã sẵn sàng, nhưng cần API trả danh sách tin nhắn để hiển thị trực tiếp trong UI.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-md">
      {messages.map((message, index) => (
        <div key={message.id ?? `${message.sender}-${message.time_text}-${index}`} className="flex gap-sm">
          <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
            <MaterialIcon name="chat_bubble" className="text-lg" />
          </div>
          <div className="border-outline-variant bg-surface rounded-2xl border px-md py-sm shadow-sm">
            <div className="mb-xs flex flex-wrap items-center gap-sm">
              <span className="text-body-sm text-on-surface font-semibold">
                {message.sender}
              </span>
              <span className="text-body-sm text-on-surface-variant">
                {message.time_text}
              </span>
            </div>
            <p className="text-body-sm text-on-surface whitespace-pre-wrap">
              {message.content}
            </p>

            {Array.isArray(message.image_urls) && message.image_urls.length > 0 ? (
              <div className="mt-sm flex flex-col gap-1">
                {message.image_urls.map((imageUrl, imageIndex) => (
                  <a
                    key={`${imageUrl}-${imageIndex}`}
                    href={imageUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary inline-flex items-center gap-1 text-sm font-semibold hover:underline"
                  >
                    <MaterialIcon name="open_in_new" className="text-base" />
                    Ảnh đính kèm {imageIndex + 1}
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
