#!/usr/bin/env node

const { Zalo, LoginQRCallbackEventType } = require("zca-js");

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function createConfig() {
  return {
    selfListen: false,
    checkUpdate: false,
    logging: false,
  };
}

async function main() {
  const sessionId = process.argv[2] || "";
  const userAgent =
    process.env.ZALO_ZCA_USER_AGENT ||
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36";

  const zalo = new Zalo(createConfig());
  let abortFn = null;

  const shutdown = () => {
    try {
      if (abortFn) abortFn();
    } catch (_) {}
    process.exit(0);
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);

  try {
    const api = await zalo.loginQR({ userAgent }, (res) => {
      if (res.type === LoginQRCallbackEventType.QRCodeGenerated) {
        abortFn = res.actions?.abort || null;
        const raw = res.data?.image || res.data?.qrData || "";
        const qrDataUrl = raw
          ? raw.startsWith("data:")
            ? raw
            : `data:image/png;base64,${raw}`
          : "";
        emit({ type: "qr", status: "waiting_scan", session_id: sessionId, qr_base64: qrDataUrl });
        return;
      }

      if (res.type === LoginQRCallbackEventType.QRCodeExpired) {
        emit({ type: "status", status: "qr_expired", session_id: sessionId });
        return;
      }

      if (res.type === LoginQRCallbackEventType.QRCodeDeclined) {
        emit({ type: "status", status: "declined", session_id: sessionId });
        return;
      }

      if (res.type === LoginQRCallbackEventType.QRCodeScanned) {
        emit({ type: "status", status: "scanned", session_id: sessionId });
      }
    });

    const context = api.getContext();
    const zaloId = api.getOwnId();
    if (!zaloId || !context) {
      throw new Error("ZCA QR login succeeded without context");
    }

    emit({
      type: "success",
      status: "confirmed",
      session_id: sessionId,
      auth: {
        cookies: JSON.stringify(context.cookie.serializeSync()),
        imei: context.imei,
        userAgent: context.userAgent,
        zaloId,
      },
    });
  } catch (err) {
    emit({
      type: "error",
      status: "error",
      session_id: sessionId,
      message: err && err.message ? err.message : String(err),
    });
    process.exitCode = 1;
  }
}

main();
