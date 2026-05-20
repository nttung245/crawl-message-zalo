/**
 * Next.js standalone không tự copy .next/static và public — thiếu bước này
 * trình duyệt 404 chunk JS và báo MIME text/plain.
 */
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const standaloneDir = path.join(root, ".next", "standalone");
const serverJs = path.join(standaloneDir, "server.js");
const staticSrc = path.join(root, ".next", "static");
const staticDest = path.join(standaloneDir, ".next", "static");
const publicSrc = path.join(root, "public");
const publicDest = path.join(standaloneDir, "public");

if (!existsSync(serverJs)) {
  console.error(
    "[copy-standalone-assets] Thiếu .next/standalone/server.js — chạy npm run build trước.",
  );
  process.exit(1);
}

if (!existsSync(staticSrc)) {
  console.error("[copy-standalone-assets] Thiếu .next/static — build Next chưa tạo static.");
  process.exit(1);
}

mkdirSync(path.join(standaloneDir, ".next"), { recursive: true });
rmSync(staticDest, { recursive: true, force: true });
cpSync(staticSrc, staticDest, { recursive: true });

if (existsSync(publicSrc)) {
  rmSync(publicDest, { recursive: true, force: true });
  cpSync(publicSrc, publicDest, { recursive: true });
}

console.log(
  "[copy-standalone-assets] Đã copy .next/static và public → .next/standalone/",
);
