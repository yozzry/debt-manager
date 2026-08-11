/**
 * خدمة جسر واتساب (Baileys) - نظام إدارة المديونيات
 * ==================================================
 *
 * خدمة Node.js صغيرة ومستقلة بتتصل بواتساب مباشرة (نفس طريقة واتساب ويب،
 * من غير API رسمي مدفوع)، وبتعرض API داخلي بسيط عشان تطبيق Flask يستخدمه
 * بدل (أو بجانب) Ultramsg.
 *
 * تشغيل: npm install && npm start (أو استخدم start_baileys.bat على ويندوز)
 *
 * ⚠️ مهم: أول تشغيل هتحتاج تمسح رمز QR من واتساب على موبايلك (من صفحة
 * "الإعدادات" -> "واتساب (Baileys)" في التطبيق). بعد كده الجلسة بتتخزن في
 * مجلد auth_session وبتفضل متصلة تلقائيًا من غير ما تحتاج تمسح QR تاني،
 * إلا لو سجلت خروج من الرقم على الموبايل نفسه.
 */
const express = require("express");
const pino = require("pino");
const QRCode = require("qrcode");
const fs = require("fs");
const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("@whiskeysockets/baileys");

const path = require("path");
const PORT = process.env.PORT || 3001;
const AUTH_FOLDER = path.join(__dirname, "auth_session");
const API_TOKEN = process.env.BAILEYS_API_TOKEN || "";

let sock = null;
let currentQr = null;
let connectionStatus = "disconnected";
let lastError = null;

// ---------------------------------------------------------------------
// Global error handlers — prevents process crash
// ---------------------------------------------------------------------
process.on("uncaughtException", (err) => {
  console.error("[FATAL] Uncaught exception:", err.message);
});
process.on("unhandledRejection", (reason) => {
  console.error("[FATAL] Unhandled rejection:", reason);
});

// ---------------------------------------------------------------------
// Phone number normalization for WhatsApp JID
// Egyptian: 010xxxxxxx → 2010xxxxxxx
// Saudi: 05xxxxxxx → 9665xxxxxxx
// If already starts with country code (no leading 0), keep as-is
// ---------------------------------------------------------------------
function normalizePhone(raw) {
  let p = String(raw).replace(/[^0-9]/g, "");
  if (p.startsWith("00")) p = p.substring(2);
  if (p.startsWith("0")) {
    // Detect country by prefix
    if (p.startsWith("01") || p.startsWith("02")) {
      p = "20" + p.substring(1); // Egypt
    } else if (p.startsWith("05")) {
      p = "966" + p.substring(1); // Saudi
    }
  }
  return p;
}

// ---------------------------------------------------------------------
// طابور إرسال بسيط بفاصل زمني عشوائي (3-8 ثواني)
// ---------------------------------------------------------------------
const sendQueue = [];
let queueRunning = false;

function randomDelayMs() {
  return 3000 + Math.floor(Math.random() * 5000);
}

async function processQueue() {
  if (queueRunning) return;
  queueRunning = true;
  while (sendQueue.length > 0) {
    const job = sendQueue.shift();
    try {
      if (!sock || connectionStatus !== "connected") {
        job.reject(new Error("WhatsApp غير متصل حاليًا"));
        continue;
      }
      const jid = `${job.to}@s.whatsapp.net`;
      await sock.sendMessage(jid, { text: job.message });
      console.log(`[SEND] OK → ${job.to}`);
      job.resolve({ ok: true });
    } catch (err) {
      console.error(`[SEND] FAIL → ${job.to}:`, err.message);
      job.reject(err);
    }
    if (sendQueue.length > 0) {
      await new Promise((r) => setTimeout(r, randomDelayMs()));
    }
  }
  queueRunning = false;
}

function queueSend(to, message) {
  return new Promise((resolve, reject) => {
    sendQueue.push({ to, message, resolve, reject });
    processQueue();
  });
}

// ---------------------------------------------------------------------
// إدارة اتصال واتساب
// ---------------------------------------------------------------------
async function startSocket() {
  try {
    connectionStatus = "connecting";
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_FOLDER);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
      version,
      auth: state,
      logger: pino({ level: "silent" }),
      printQRInTerminal: false,
      connectTimeout: 30000,
      browser: ["Debt Manager", "Chrome", "120.0"],
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        currentQr = await QRCode.toDataURL(qr);
        connectionStatus = "qr";
        console.log("Baileys: QR code generated — scan from phone.");
      }

      if (connection === "open") {
        connectionStatus = "connected";
        currentQr = null;
        lastError = null;
        console.log("Baileys: Connected to WhatsApp.");
      }

      if (connection === "close") {
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const loggedOut = statusCode === DisconnectReason.loggedOut;
        connectionStatus = "disconnected";
        currentQr = null;

        if (loggedOut) {
          console.log("Baileys: Logged out — need new QR scan.");
          lastError = "تم تسجيل الخروج من الرقم - امسح رمز QR تاني للربط من جديد";
        } else {
          lastError = "انقطع الاتصال، جاري إعادة المحاولة...";
          console.log("Baileys: Disconnected, reconnecting in 3s...");
          setTimeout(startSocket, 3000);
        }
      }
    });

    sock.ev.on("messages.upsert", () => {});
  } catch (err) {
    console.error("Baileys: Failed to start socket:", err.message);
    connectionStatus = "disconnected";
    lastError = "فشل بدء خدمة Baileys: " + err.message;
  }
}

// ---------------------------------------------------------------------
// Express API
// ---------------------------------------------------------------------
const app = express();
app.use(express.json());

app.use((req, res, next) => {
  if (!API_TOKEN) return next();
  if (req.headers["x-api-token"] === API_TOKEN) return next();
  return res.status(401).json({ success: false, error: "Unauthorized" });
});

app.get("/status", (req, res) => {
  res.json({
    status: connectionStatus,
    qr: currentQr,
    error: lastError,
  });
});

app.post("/send", async (req, res) => {
  const { to, message } = req.body || {};
  if (!to || !message) {
    return res
      .status(400)
      .json({ success: false, error: "to and message are required" });
  }
  if (!sock || connectionStatus !== "connected") {
    return res
      .status(503)
      .json({ success: false, error: "WhatsApp غير متصل حاليًا" });
  }

  const phone = normalizePhone(to);
  const jid = `${phone}@s.whatsapp.net`;

  try {
    await Promise.race([
      sock.sendMessage(jid, { text: message }),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error("WhatsApp send timeout")), 30000)
      ),
    ]);
    console.log(`[API /send] OK → ${phone}`);
    res.json({ success: true });
  } catch (err) {
    console.error(`[API /send] FAIL → ${phone}:`, err.message);
    res.status(502).json({ success: false, error: err.message });
  }
});

app.post("/logout", async (req, res) => {
  try {
    if (sock) await sock.logout();
  } catch (err) {
    // ignore
  }
  try {
    fs.rmSync(AUTH_FOLDER, { recursive: true, force: true });
  } catch (err) {
    // ignore
  }
  connectionStatus = "disconnected";
  currentQr = null;
  lastError = null;
  res.json({ success: true });
  setTimeout(() => startSocket(), 1000);
});

app.listen(PORT, "127.0.0.1", () => {
  console.log(`Baileys bridge listening on http://127.0.0.1:${PORT}`);
  startSocket();
});
