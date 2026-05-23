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
        {"Backend hi\u1ec7n m\u1edbi tr\u1ea3 v\u1ec1 ti\u1ebfn \u0111\u1ed9 t\u1ed5ng h\u1ee3p cho job. Timeline \u0111\u00e3 s\u1eb5n s\u00e0ng, nh\u01b0ng c\u1ea7n API tr\u1ea3 danh s\u00e1ch tin nh\u1eafn \u0111\u1ec3 hi\u1ec3n th\u1ecb tr\u1ef1c ti\u1ebfp trong UI."}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-md">
      {messages.map((message, index) => (
        <div
          key={message.id ?? `${message.sender}-${message.time_text}-${index}`}
          className="flex gap-sm"
        >
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
                    {"\u1ea2nh \u0111\u00ednh k\u00e8m "} {imageIndex + 1}
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
