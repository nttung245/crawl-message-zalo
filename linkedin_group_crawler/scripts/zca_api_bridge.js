#!/usr/bin/env node

const { Zalo, ThreadType } = require("zca-js");
const fs = require("fs");
const path = require("path");
const { imageSize } = require("image-size");

function emitAndExit(payload, code = 0) {
  const data = `${JSON.stringify(payload)}\n`;
  if (process.stdout.write(data)) {
    process.exit(code);
  } else {
    process.stdout.once('drain', () => process.exit(code));
  }
}

function safeJson(value) {
  try {
    return JSON.stringify(value);
  } catch (_error) {
    return String(value);
  }
}

function serializeError(error) {
  if (!error) return { message: "Unknown error" };
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
  return { message: String(error) };
}

function fail(error) {
  const serialized = serializeError(error);
  emitAndExit({
    ok: false,
    error: serialized.message,
    error_detail: serialized,
  }, 1);
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
  const args = { command: argv[2] || "" };
  for (let i = 3; i < argv.length; i += 1) {
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

async function login(auth, options = {}) {
  const cookie = normalizeCookieJar(auth.cookies);
  if (!cookie || !auth.imei || !auth.userAgent) {
    throw new Error("Missing ZCA auth fields: cookies, imei, userAgent");
  }

  const zalo = new Zalo({
    selfListen: Boolean(options.selfListen),
    checkUpdate: false,
    logging: false,
  });
  return await zalo.login({
    cookie,
    imei: auth.imei,
    userAgent: auth.userAgent,
  });
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

function toTimestampMs(value) {
  if (value == null || value === "") return 0;

  if (typeof value === "number") {
    if (!Number.isFinite(value)) return 0;
    return value < 10000000000 ? Math.floor(value * 1000) : Math.floor(value);
  }

  const text = String(value).trim();
  if (!text) return 0;

  if (/^\d+$/.test(text)) {
    const n = Number(text);
    if (!Number.isFinite(n)) return 0;
    return n < 10000000000 ? Math.floor(n * 1000) : Math.floor(n);
  }

  const parsed = Date.parse(text);
  return Number.isFinite(parsed) ? parsed : 0;
}

function firstTimestampMs(...values) {
  for (const value of values) {
    const ts = toTimestampMs(value);
    if (ts > 0) return ts;
  }
  return 0;
}

function sortMessagesOldToNew(messages) {
  return [...messages].sort((a, b) => {
    const tA = toTimestampMs(a.timestamp || a.time_text);
    const tB = toTimestampMs(b.timestamp || b.time_text);
    if (tA !== tB) return tA - tB;
    return String(a.message_id || "").localeCompare(String(b.message_id || ""));
  });
}

function normalizeGroup(groupId, raw) {
  const source = raw || {};
  const lastRaw = source.lastMsg || source.lastMessage || source.msg || source.preview || null;

  const id = String(
    groupId ||
      source.group_id ||
      source.groupId ||
      source.grid ||
      source.id ||
      source.threadId ||
      source.conversationId ||
      ""
  );

  const name = String(
    source.name ||
      source.group_name ||
      source.displayName ||
      source.groupName ||
      source.title ||
      source.topic ||
      source.shortName ||
      source.fullName ||
      source.globalId ||
      source.grid ||
      source.id ||
      groupId ||
      id
  );

  const lastMessageAt = firstTimestampMs(
    source.last_message_at,
    source.lastMessageAt,
    source.lastMsgAt,
    source.lastMsgTime,
    source.lastTime,
    source.updateTime,
    source.updatedAt,
    source.ts,
    source.time,
    lastRaw && lastRaw.ts,
    lastRaw && lastRaw.time,
    lastRaw && lastRaw.timestamp,
    lastRaw && lastRaw.createdAt
  );

  return {
    group_id: id,
    name,
    avatar_url: source.avatar || source.avt || source.fullAvt || source.avatarUrl || source.fullAvatar || null,
    last_message: textOf(lastRaw) || null,
    last_message_at: lastMessageAt || null,
    unread_count: Number(source.unreadCount || source.unread || 0) || 0,
    is_pinned: Boolean(source.isPinned || source.pinned || source.pin || source.isPin),
    raw: source,
  };
}

function normalizeConversation(groupId, raw) {
  const source = raw || {};
  const lastRaw = source.lastMsg || source.lastMessage || source.msg || source.preview || null;

  const id = String(
    groupId ||
      source.group_id ||
      source.groupId ||
      source.grid ||
      source.id ||
      source.threadId ||
      source.conversationId ||
      source.userId ||
      ""
  );

  const name = String(
    source.name ||
      source.group_name ||
      source.displayName ||
      source.groupName ||
      source.title ||
      source.topic ||
      id
  );

  const lastMessageAt = firstTimestampMs(
    source.last_message_at,
    source.lastMessageAt,
    source.lastMsgAt,
    source.lastMsgTime,
    source.lastTime,
    source.updateTime,
    source.updatedAt,
    source.ts,
    source.time,
    lastRaw && lastRaw.ts,
    lastRaw && lastRaw.time,
    lastRaw && lastRaw.timestamp,
    lastRaw && lastRaw.createdAt
  );

  return {
    group_id: id,
    name,
    avatar_url: source.avatar || source.avt || source.fullAvt || source.avatarUrl || null,
    last_message: textOf(lastRaw) || null,
    last_message_at: lastMessageAt || null,
    unread_count: Number(source.unreadCount || source.unread || 0) || 0,
    raw: source,
  };
}

function normalizeGroups(response) {
  const groups = [];
  const seen = new Set();

  const add = (groupId, raw) => {
    const group = normalizeGroup(groupId, raw);
    if (!group.group_id || seen.has(group.group_id)) return;
    seen.add(group.group_id);
    groups.push(group);
  };

  if (Array.isArray(response)) {
    for (const item of response) add(null, item);
  } else if (response && typeof response === "object") {
    for (const key of ["groups", "data", "items", "list"]) {
      for (const item of valuesFromUnknown(response[key])) add(null, item);
    }
    const gridVerMap = response.gridVerMap || response.gridInfoMap || response.groupInfoMap;
    if (gridVerMap && typeof gridVerMap === "object") {
      for (const [groupId, raw] of Object.entries(gridVerMap)) add(groupId, raw);
    }
    for (const [key, raw] of Object.entries(response)) {
      if (/^\d+$/.test(String(key))) add(key, raw);
    }
  }

  return groups;
}

function groupIdsFromAllGroups(response) {
  const ids = [];
  const add = (value) => {
    const id = String(value || "").trim();
    if (id && !ids.includes(id)) ids.push(id);
  };

  if (Array.isArray(response)) {
    for (const item of response) {
      if (typeof item === "string" || typeof item === "number") add(item);
      else add(item.groupId || item.grid || item.id || item.threadId);
    }
    return ids;
  }

  if (response && typeof response === "object") {
    for (const key of ["gridVerMap", "gridInfoMap", "groupInfoMap"]) {
      const map = response[key];
      if (map && typeof map === "object") {
        for (const groupId of Object.keys(map)) add(groupId);
      }
    }
    for (const key of ["groups", "data", "items", "list"]) {
      for (const item of valuesFromUnknown(response[key])) {
        if (typeof item === "string" || typeof item === "number") add(item);
        else add(item.groupId || item.grid || item.id || item.threadId);
      }
    }
  }

  return ids;
}

async function enrichGroupWithLatestMessage(api, group) {
  // Chỉ gọi getGroupChatHistory khi getGroupInfo không cho đủ last_message_at.
  // Lấy 20 tin rồi chọn tin mới nhất để tránh trường hợp tin cuối là system message rỗng.
  if (toTimestampMs(group.last_message_at) > 0 && group.last_message) {
    return group;
  }

  try {
    const response = await api.getGroupChatHistory(String(group.group_id), 20);
    const messages = normalizeHistory(response); // sorted old -> new
    const latest = messages[messages.length - 1] || null;

    if (!latest) {
      return {
        ...group,
        last_message_at: group.last_message_at || null,
      };
    }

    return {
      ...group,
      last_message: latest.content || group.last_message || null,
      last_message_at: latest.timestamp || latest.time_text || group.last_message_at || null,
      last_sender_id: latest.sender_id || group.last_sender_id || null,
      last_sender_name: latest.sender_name || group.last_sender_name || null,
      last_message_type: latest.type || group.last_message_type || null,
    };
  } catch (error) {
    return {
      ...group,
      last_message_at: group.last_message_at || null,
      latest_error: serializeError(error).message,
    };
  }
}

async function enrichGroupsWithLatestMessages(api, groups, concurrency = 4) {
  const result = new Array(groups.length);
  let index = 0;

  async function worker() {
    while (index < groups.length) {
      const current = index;
      index += 1;
      result[current] = await enrichGroupWithLatestMessage(api, groups[current]);
    }
  }

  const workers = Array.from(
    { length: Math.min(concurrency, Math.max(1, groups.length)) },
    () => worker()
  );

  await Promise.all(workers);
  return result;
}

function sortGroupsLikeZalo(groups) {
  return [...groups].sort((a, b) => {
    // 1. Pinned luôn đứng trước.
    const pinA = a.is_pinned ? 1 : 0;
    const pinB = b.is_pinned ? 1 : 0;
    if (pinA !== pinB) return pinB - pinA;

    // 2. last_message_at DESC. Group không có last_message_at (=0) bị đẩy xuống dưới.
    const tA = toTimestampMs(a.last_message_at);
    const tB = toTimestampMs(b.last_message_at);
    if (tA !== tB) return tB - tA;

    // 3. Tie-break theo tên. KHÔNG dùng unread_count làm thứ tự chính.
    return String(a.name || "").localeCompare(String(b.name || ""));
  });
}

async function listGroups(api) {
  const allGroupsResponse = await api.getAllGroups();
  const groupIds = groupIdsFromAllGroups(allGroupsResponse);

  if (!groupIds.length) {
    const groups = normalizeGroups(allGroupsResponse);
    const enriched = await enrichGroupsWithLatestMessages(api, groups, 5);

    return {
      groups: sortGroupsLikeZalo(enriched),
      raw_shape: Object.keys(allGroupsResponse || {}),
      source: "getAllGroups+latestMessage",
    };
  }

  const groups = [];
  const errors = [];

  for (let index = 0; index < groupIds.length; index += 50) {
    const chunk = groupIds.slice(index, index + 50);

    try {
      const infoResponse = await api.getGroupInfo(chunk);
      const infoGroups = normalizeGroups(infoResponse);
      groups.push(...infoGroups);
    } catch (error) {
      errors.push(serializeError(error));

      for (const groupId of chunk) {
        groups.push(normalizeConversation(groupId, { grid: groupId }));
      }
    }
  }

  const normalized = normalizeGroups(groups);
  const enriched = await enrichGroupsWithLatestMessages(api, normalized, 5);

  return {
    groups: sortGroupsLikeZalo(enriched),
    raw_shape: Object.keys(allGroupsResponse || {}),
    source: errors.length
      ? "getAllGroups+partial_getGroupInfo+latestMessage"
      : "getAllGroups+getGroupInfo+latestMessage",
    group_count_from_getAllGroups: groupIds.length,
    warnings: errors,
  };
}

async function relatedGroupIds(api, groupId) {
  const ids = [];
  const add = (value) => {
    const id = String(value || "").trim();
    if (id && !ids.includes(id)) ids.push(id);
  };

  add(groupId);
  const infoResponse = await api.getGroupInfo([String(groupId)]);
  const groups = normalizeGroups(infoResponse);
  for (const group of groups) {
    add(group.group_id);
    const raw = group.raw || {};
    add(raw.groupId);
    add(raw.group_id);
    add(raw.globalId);
    add(raw.grid);
    add(raw.id);
  }

  return {
    ids,
    groups,
    raw_shape: Object.keys(infoResponse || {}),
  };
}

function normalizeMessage(raw, index) {
  const data = raw && raw.data ? raw.data : raw || {};
  const content = data.content ?? data.message ?? data.msg ?? raw.content ?? raw.message;
  const imageUrls = collectUrls(content).concat(collectUrls(data.attachments || data.attachment || data.photos));
  const msgType = String(data.msgType || data.type || raw.type || "text");
  const messageId = String(
    data.msgId ||
      data.cliMsgId ||
      data.realMsgId ||
      raw.msgId ||
      raw.messageId ||
      raw.id ||
      `${data.ts || Date.now()}-${index}`
  );
  const timestampMs = firstTimestampMs(
    data.ts,
    data.time,
    data.timestamp,
    raw.timestamp,
    raw.ts,
    raw.time,
    raw.createdAt,
    data.createdAt
  );
  const timestamp = timestampMs || null;
  let contentText = textOf(content);
  if (imageUrls.length > 0 && contentText) {
    const trimmed = contentText.trim();
    if (imageUrls.includes(trimmed) || isLikelyImageUrl(trimmed)) {
      contentText = "";
    }
  }

  return {
    message_id: messageId,
    sender_id: String(data.uidFrom || raw.uidFrom || raw.senderId || raw.sender_id || ""),
    sender_name: data.dName || data.displayName || raw.senderName || raw.sender_name || null,
    timestamp: timestamp ? String(timestamp) : null,
    time_text: timestamp ? new Date(Number(timestamp)).toISOString() : null,
    type: imageUrls.length ? "image" : msgType,
    content: contentText || null,
    image_urls: Array.from(new Set(imageUrls)),
    reply_to_id: data.quote?.msgId || data.quoteMsgId || null,
    is_deleted: msgType === "chat.delete" || msgType === "recalled",
    is_sent: Boolean(raw.isSelf || data.isSelf),
    group_id: String(raw.threadId || raw.data?.idTo || raw.data?.threadId || "") || null,
    raw,
  };
}

function toTimestampMs(value) {
  if (value == null || value === "") return 0;

  if (typeof value === "number") {
    if (!Number.isFinite(value)) return 0;
    return value < 10000000000 ? Math.floor(value * 1000) : Math.floor(value);
  }

  const text = String(value).trim();
  if (!text) return 0;

  if (/^\d+$/.test(text)) {
    const n = Number(text);
    if (!Number.isFinite(n)) return 0;
    return n < 10000000000 ? Math.floor(n * 1000) : Math.floor(n);
  }

  const parsed = Date.parse(text);
  return Number.isFinite(parsed) ? parsed : 0;
}

function sortMessagesOldToNew(messages) {
  return [...messages].sort((a, b) => {
    const tA = toTimestampMs(a.timestamp || a.time_text);
    const tB = toTimestampMs(b.timestamp || b.time_text);
    if (tA !== tB) return tA - tB;
    return String(a.message_id || "").localeCompare(String(b.message_id || ""));
  });
}

function extractMessageList(response) {
  if (Array.isArray(response)) return response;

  if (!response || typeof response !== "object") return [];

  const directKeys = [
    "messages",
    "items",
    "list",
    "groupMsgs",
    "msgs",
  ];

  for (const key of directKeys) {
    if (Array.isArray(response[key])) return response[key];
  }

  const data = response.data;
  if (Array.isArray(data)) return data;

  if (data && typeof data === "object") {
    for (const key of directKeys) {
      if (Array.isArray(data[key])) return data[key];
    }

    for (const value of Object.values(data)) {
      if (Array.isArray(value)) return value;
      if (value && typeof value === "object") {
        for (const key of directKeys) {
          if (Array.isArray(value[key])) return value[key];
        }
      }
    }
  }

  return [];
}

function normalizeHistory(response) {
  const list = extractMessageList(response);
  const normalized = list
    .map((item, index) => normalizeMessage(item, index))
    .filter((msg) => msg && msg.message_id);

  return sortMessagesOldToNew(normalized);
}

async function syncOldMessages(auth, threadType, threadId, count, timeoutMs) {
  const api = await login(auth, { selfListen: true });
  const listener = api.listener;
  if (!listener || typeof listener.start !== "function") {
    throw new Error("ZCA listener is not available");
  }

  const wantedThreadId = String(threadId || "");
  const collected = [];
  const seen = new Set();
  const threadCounts = {};
  let requestCount = 0;
  let lastMsgId = null;
  let noMoreMessages = false;
  let pendingRequest = false;

  const addMessages = (messages) => {
    let addedCount = 0;
    for (const raw of Array.isArray(messages) ? messages : []) {
      const rawThreadId = String(raw.threadId || raw.data?.idTo || raw.data?.threadId || "");
      if (rawThreadId) threadCounts[rawThreadId] = (threadCounts[rawThreadId] || 0) + 1;
      if (wantedThreadId && rawThreadId !== wantedThreadId) continue;
      
      const normalized = normalizeMessage(raw, collected.length);
      if (!normalized.message_id || seen.has(normalized.message_id)) continue;
      seen.add(normalized.message_id);
      collected.push(normalized);
      addedCount++;

      const zMsgId = raw.msgId || raw.messageId || (raw.data && (raw.data.msgId || raw.data.cliMsgId || raw.data.realMsgId));
      if (zMsgId) {
        lastMsgId = String(zMsgId);
      }
    }
    return addedCount;
  };

  return await new Promise((resolve, reject) => {
    let finished = false;
    let requestTimer = null;
    let attempt = 0;

    const done = (error) => {
      if (finished) return;
      finished = true;
      clearTimeout(globalTimer);
      clearTimeout(requestTimer);
      try {
        if (typeof listener.stop === "function") listener.stop();
      } catch (_error) {}
      if (error) reject(error);
      else {
        // Sort from newest to oldest (timestamp descending)
        collected.sort((a, b) => {
          const tA = a.timestamp ? Number(a.timestamp) : 0;
          const tB = b.timestamp ? Number(b.timestamp) : 0;
          return tB - tA;
        });
        resolve({
          messages: collected.slice(0, count),
          diagnostics: {
            requested_thread_id: wantedThreadId,
            request_count: requestCount,
            thread_counts: threadCounts,
            last_msg_id: lastMsgId,
            no_more_messages: noMoreMessages,
          },
        });
      }
    };

    const globalTimer = setTimeout(() => done(), timeoutMs);

    const sendRequest = () => {
      if (finished || noMoreMessages || collected.length >= count) return;
      
      pendingRequest = true;
      requestCount += 1;
      listener.requestOldMessages(threadType, lastMsgId);
      
      // Retry timer (5 seconds)
      clearTimeout(requestTimer);
      requestTimer = setTimeout(() => {
        if (pendingRequest && !finished) {
          attempt += 1;
          if (attempt >= 3) {
            done();
          } else {
            sendRequest();
          }
        }
      }, 5000);
    };

    listener.on("old_messages", (messages, type) => {
      if (Number(type) !== Number(threadType)) return;
      clearTimeout(requestTimer);
      pendingRequest = false;
      attempt = 0;
      
      const added = addMessages(messages);
      if (!messages || messages.length === 0 || added === 0) {
        noMoreMessages = true;
        done();
        return;
      }
      
      if (collected.length >= count) {
        done();
      } else {
        // Sleep 400ms between page requests to avoid rate limits
        setTimeout(sendRequest, 400);
      }
    });

    listener.on("message", (message) => {
      const messageThreadId = String(message.threadId || message.data?.idTo || "");
      if (wantedThreadId && messageThreadId !== wantedThreadId) return;
      addMessages([message]);
      if (collected.length >= count) done();
    });

    listener.on("connected", () => {
      sendRequest();
    });
    
    listener.on("error", (error) => reject(error));
    listener.on("closed", () => done());
    listener.on("disconnected", () => done());

    try {
      listener.start();
    } catch (error) {
      done(error);
    }
  });
}

async function main() {
  const args = parseArgs(process.argv);
  const input = await readStdinJson();
  const auth = input.auth || input.zca_auth || input;
  const needsListener = args.command === "sync-old-messages";
  const api = needsListener ? null : await login(auth);

  if (args.command === "debug-auth") {
    emitAndExit({
      ok: true,
      own_id: typeof api.getOwnId === "function" ? api.getOwnId() : null,
      api_methods: Object.keys(api).filter((key) => typeof api[key] === "function").sort(),
      auth_shape: {
        has_cookies: Boolean(auth.cookies),
        cookie_type: Array.isArray(auth.cookies) ? "array" : typeof auth.cookies,
        has_imei: Boolean(auth.imei),
        has_userAgent: Boolean(auth.userAgent),
        has_zaloId: Boolean(auth.zaloId),
      },
    }, 0);
    return;
  }

  if (args.command === "list-groups") {
    emitAndExit({ ok: true, ...(await listGroups(api)) }, 0);
    return;
  }

  if (args.command === "list-friends") {
    const friends = await api.getAllFriends();
    const normalized = (Array.isArray(friends) ? friends : []).map((f) => ({
      group_id: String(f.userId || ""),
      name: String(f.displayName || f.zaloName || ""),
      avatar_url: String(f.avatar || f.avatarUrl || ""),
      unread_count: 0,
    }));
    emitAndExit({ ok: true, friends: normalized }, 0);
    return;
  }

  if (args.command === "group-history") {
  const groupId = args["group-id"] || input.group_id || input.groupId;
  const count = Math.max(50, Math.min(Number(args.count || input.count || 1000), 3000));

  if (!groupId) throw new Error("Missing --group-id");

  const response = await api.getGroupChatHistory(String(groupId), count);
  const messages = normalizeHistory(response);

  emitAndExit({
    ok: true,
    messages,
    message_count: messages.length,
    requested_count: count,
    raw_shape: Object.keys(response || {}),
    source: "getGroupChatHistory",
  }, 0);
  return;
}

  if (args.command === "group-related-ids") {
    const groupId = args["group-id"] || input.group_id || input.groupId;
    if (!groupId) throw new Error("Missing --group-id");
    emitAndExit({ ok: true, ...(await relatedGroupIds(api, groupId)) }, 0);
    return;
  }

  if (args.command === "sync-old-messages") {
    const threadId = args["thread-id"] || input.thread_id || input.threadId || input.group_id || input.groupId;
    const type = Number(args.type || input.type || ThreadType.Group);
    const count = Number(args.count || input.count || 500);
    const timeoutMs = Number(args.timeout || input.timeout_ms || input.timeoutMs || 35000);
    // threadId can be empty or undefined for global synchronization
    const result = await syncOldMessages(auth, type, threadId ? String(threadId) : "", count, timeoutMs);
    emitAndExit({ ok: true, ...result, source: "listener.requestOldMessages" }, 0);
    return;
  }

  if (args.command === "send-message") {
    const threadId = args["thread-id"] || input.thread_id || input.threadId;
    const type = Number(args.type || input.type || ThreadType.Group);
    const text = args.text || input.text || input.message || "";
    if (!threadId) throw new Error("Missing --thread-id");
    const response = await api.sendMessage({ msg: text }, String(threadId), type);
    emitAndExit({ ok: true, response }, 0);
    return;
  }

  if (args.command === "send-images") {
    const threadId = args["thread-id"] || input.thread_id || input.threadId;
    const type = Number(args.type || input.type || ThreadType.Group);
    const text = args.text || input.text || input.message || "";
    const filePaths = input.file_paths || input.filePaths || [];
    if (!threadId) throw new Error("Missing --thread-id");
    if (!Array.isArray(filePaths) || !filePaths.length) throw new Error("Missing file_paths");

    const attachments = filePaths.map((filePath) => {
      const buffer = fs.readFileSync(filePath);
      const baseName = path.basename(filePath);
      let width = 0;
      let height = 0;
      try {
        const dim = imageSize(buffer);
        width = dim.width || 0;
        height = dim.height || 0;
      } catch (_error) {}
      return {
        data: buffer,
        filename: path.extname(baseName) ? baseName : `${baseName}.jpg`,
        metadata: {
          totalSize: buffer.length,
          width,
          height,
        },
      };
    });
    const response = await api.sendMessage({ msg: text, attachments }, String(threadId), type);
    emitAndExit({ ok: true, response }, 0);
    return;
  }

  if (args.command === "remove-unread") {
    const threadId = args["thread-id"] || input.thread_id || input.threadId;
    const type = Number(args.type || input.type || ThreadType.Group);
    if (!threadId) throw new Error("Missing --thread-id");
    const response = await api.removeUnreadMark(String(threadId), type);
    emitAndExit({ ok: true, response }, 0);
    return;
  }

  throw new Error(`Unknown command: ${args.command}`);
}

main().catch(fail);
