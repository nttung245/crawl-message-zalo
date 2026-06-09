#!/usr/bin/env node

const { Zalo, ThreadType } = require("zca-js");

function safeJson(value) {
  try {
    return JSON.stringify(value);
  } catch (_error) {
    return String(value);
  }
}

function emit(payload) {
  process.stdout.write(`${JSON.stringify({ ts: Date.now(), ...payload })}\n`);
}

function serializeError(error) {
  if (!error) return { name: "Error", message: "Unknown error", code: null };
  if (error instanceof Error) {
    return {
      name: error.name || "Error",
      message: error.message || String(error),
      code: error.code ?? null,
      stack: error.stack || null,
    };
  }
  if (typeof error === "object") {
    return {
      name: error.name || "NonError",
      message: error.message || safeJson(error),
      code: error.code ?? null,
      raw: error,
    };
  }
  return { name: "Error", message: String(error), code: null };
}

function readStdinJson() {
  return new Promise((resolve, reject) => {
    let raw = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      raw += chunk;
    });
    process.stdin.on("end", () => {
      try {
        resolve(raw.trim() ? JSON.parse(raw) : {});
      } catch (error) {
        reject(error);
      }
    });
    process.stdin.on("error", reject);
  });
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) continue;
    const name = key.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[name] = true;
    } else {
      args[name] = next;
      i += 1;
    }
  }
  return args;
}

function normalizeCookieJar(cookies) {
  if (!cookies) return null;
  if (typeof cookies === "string") return JSON.parse(cookies);
  return cookies;
}

function valuesFromUnknown(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (typeof value === "object") return Object.values(value);
  return [];
}

function textOf(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(textOf).filter(Boolean).join(" ");
  if (typeof value === "object") {
    return (
      value.title ||
      value.text ||
      value.msg ||
      value.message ||
      value.description ||
      value.href ||
      ""
    );
  }
  return "";
}

function isLikelyImageUrl(value) {
  if (!/^https?:\/\//i.test(value)) return false;
  if (/\.(png|jpe?g|webp|gif)(\?|#|$)/i.test(value)) return true;
  return /(photo|image|img|thumb|avatar|zalo|zstatic|zadn|zaloapp)/i.test(value);
}

function collectUrls(value, out = []) {
  if (!value) return out;
  if (typeof value === "string") {
    if (isLikelyImageUrl(value)) out.push(value);
    return out;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectUrls(item, out);
    return out;
  }
  if (typeof value === "object") {
    let found = false;
    for (const key of ["hdUrl", "normalUrl", "url", "imageUrl", "photoUrl", "src", "fileUrl", "href"]) {
      if (value[key] && typeof value[key] === "string" && isLikelyImageUrl(value[key])) {
        out.push(value[key]);
        found = true;
        break;
      }
    }
    if (found) {
      return Array.from(new Set(out));
    }
    for (const item of Object.values(value)) collectUrls(item, out);
  }
  return Array.from(new Set(out));
}

function normalizeMessage(raw, index, ownId = null) {
  const data = raw && raw.data ? raw.data : raw || {};
  const content = data.content ?? data.message ?? data.msg ?? raw.content ?? raw.message;
  const imageUrls = collectUrls(content).concat(collectUrls(data.attachments || data.attachment || data.photos));
  const msgType = String(data.msgType || data.type || raw.type || "text");
  const threadId = String(
    raw.threadId ||
      data.idTo ||
      data.threadId ||
      raw.idTo ||
      data.groupId ||
      raw.groupId ||
      ""
  );
  const messageId = String(
    data.msgId ||
      data.cliMsgId ||
      data.realMsgId ||
      raw.msgId ||
      raw.messageId ||
      raw.id ||
      `${data.ts || Date.now()}-${index}`
  );
  const timestamp = data.ts || raw.timestamp || raw.ts || raw.time || null;
  let contentText = textOf(content);
  if (imageUrls.length > 0 && contentText) {
    const trimmed = contentText.trim();
    if (imageUrls.includes(trimmed) || isLikelyImageUrl(trimmed)) {
      contentText = "";
    }
  }
  const senderId = String(data.uidFrom || raw.uidFrom || raw.senderId || raw.sender_id || "");

  return {
    thread_id: threadId,
    message_id: messageId,
    sender_id: senderId,
    sender_name: data.dName || data.displayName || raw.senderName || raw.sender_name || null,
    timestamp: timestamp ? String(timestamp) : null,
    time_text: timestamp ? new Date(Number(timestamp)).toISOString() : null,
    type: imageUrls.length ? "image" : msgType,
    content: contentText || null,
    image_urls: Array.from(new Set(imageUrls)),
    reply_to_id: data.quote?.msgId || data.quoteMsgId || null,
    is_deleted: msgType === "chat.delete" || msgType === "recalled",
    is_sent: Boolean(raw.isSelf || data.isSelf || (ownId && String(senderId) === String(ownId))),
  };
}

async function login(auth) {
  const cookie = normalizeCookieJar(auth.cookies);
  if (!cookie || !auth.imei || !auth.userAgent) {
    throw new Error("Missing ZCA auth fields: cookies, imei, userAgent");
  }
  const zalo = new Zalo({
    selfListen: true,
    checkUpdate: false,
    logging: false,
  });
  return await zalo.login({
    cookie,
    imei: auth.imei,
    userAgent: auth.userAgent,
  });
}

async function requestOldMessages(listener) {
  try {
    if (listener && typeof listener.requestOldMessages === "function") {
      listener.requestOldMessages(ThreadType.Group, null);
      emit({ event: "old_messages_requested", type: ThreadType.Group });
      if (ThreadType.User !== undefined) {
        listener.requestOldMessages(ThreadType.User, null);
        emit({ event: "old_messages_requested", type: ThreadType.User });
      }
    }
  } catch (error) {
    emit({ event: "error", error: "request_old_messages_failed", error_detail: serializeError(error) });
  }
}

async function main() {
  const args = parseArgs(process.argv);
  const input = await readStdinJson();
  const userId = String(args["user-id"] || input.user_id || "default");
  const oldMessageIntervalMs = Number(args["old-message-interval-ms"] || 300000);
  const auth = input.auth || input.zca_auth || input;

  emit({ event: "starting", user_id: userId });
  const api = await login(auth);
  const ownId = typeof api.getOwnId === "function" ? api.getOwnId() : null;
  const listener = api.listener;
  if (!listener || typeof listener.start !== "function") {
    throw new Error("ZCA listener is not available");
  }

  let stopping = false;
  let oldMessageTimer = null;

  const stop = (signal) => {
    if (stopping) return;
    stopping = true;
    if (oldMessageTimer) clearInterval(oldMessageTimer);
    emit({ event: "stopping", user_id: userId, signal });
    try {
      if (typeof listener.stop === "function") listener.stop();
    } catch (error) {
      emit({ event: "error", error: "listener_stop_failed", error_detail: serializeError(error) });
    }
    setTimeout(() => process.exit(0), 250).unref();
  };

  process.on("SIGTERM", () => stop("SIGTERM"));
  process.on("SIGINT", () => stop("SIGINT"));

  listener.on("connected", () => {
    emit({ event: "connected", user_id: userId, own_id: typeof api.getOwnId === "function" ? api.getOwnId() : null });
    requestOldMessages(listener);
    if (!oldMessageTimer) {
      oldMessageTimer = setInterval(() => requestOldMessages(listener), oldMessageIntervalMs);
    }
  });
  listener.on("disconnected", (code, reason) => {
    emit({ event: "disconnected", user_id: userId, code, reason: reason ? String(reason) : null });
  });
  listener.on("closed", (code, reason) => {
    emit({ event: "closed", user_id: userId, code, reason: reason ? String(reason) : null });
  });
  listener.on("error", (error) => {
    emit({ event: "error", user_id: userId, error: "listener_error", error_detail: serializeError(error) });
  });
  listener.on("message", (message) => {
    const normalized = normalizeMessage(message, 0, ownId);
    if (normalized.thread_id && normalized.message_id) {
      emit({ event: "message", user_id: userId, message: normalized });
    }
  });
  listener.on("old_messages", (messages, type) => {
    const numericType = Number(type);
    if (
      numericType !== Number(ThreadType.Group) &&
      numericType !== Number(ThreadType.User)
    ) {
      return;
    }
    const normalized = valuesFromUnknown(messages)
      .map((message, index) => normalizeMessage(message, index, ownId))
      .filter((message) => message.thread_id && message.message_id);
    emit({ event: "old_messages", user_id: userId, type, messages: normalized });
  });

  listener.start({ retryOnClose: true });
  emit({ event: "ready", user_id: userId, pid: process.pid });
}

main().catch((error) => {
  emit({ event: "fatal", error: "listener_fatal", error_detail: serializeError(error) });
  process.exit(1);
});
