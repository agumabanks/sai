/**
 * Sanaa AI — WhatsApp Baileys Sidecar
 *
 * Node.js process that bridges WhatsApp Web (via Baileys) to the Python
 * agent over a local WebSocket on port 3001.
 *
 * Protocol (JSON over WebSocket):
 *   Python → Sidecar:
 *     { type: "connect" }                    — start/restart Baileys
 *     { type: "send_message", to, text }     — send text message
 *     { type: "send_media", to, url, media_type, caption }
 *     { type: "status" }                     — request connection status
 *
 *   Sidecar → Python:
 *     { type: "qr", data: "<qr_string>" }         — QR code for pairing
 *     { type: "connected", phone: "2567..." }      — connection established
 *     { type: "disconnected", reason: "..." }      — connection lost
 *     { type: "message", data: { id, from, text, timestamp, ... } }
 *     { type: "status", data: { connected, phone } }
 */

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
} = require("@whiskeysockets/baileys");

const { WebSocketServer } = require("ws");
const path = require("path");
const pino = require("pino");

const AUTH_DIR = path.join(__dirname, "auth");
const WS_PORT = parseInt(process.env.WA_SIDECAR_PORT || "3001", 10);

const logger = pino({ level: process.env.LOG_LEVEL || "warn" });

let sock = null;
let pythonWs = null;
let connectionState = { connected: false, phone: null };

// ==================== WEBSOCKET SERVER ====================

const wss = new WebSocketServer({ port: WS_PORT, host: "127.0.0.1" });
console.log(`[sidecar] WebSocket server listening on 127.0.0.1:${WS_PORT}`);

wss.on("connection", (ws) => {
  console.log("[sidecar] Python adapter connected");
  pythonWs = ws;

  // Send current status immediately
  sendToPython({ type: "status", data: connectionState });

  ws.on("message", async (raw) => {
    try {
      const msg = JSON.parse(raw.toString());

      switch (msg.type) {
        case "connect":
          await startBaileys();
          break;

        case "send_message":
          if (sock) {
            await sock.sendMessage(msg.to, { text: msg.text });
          }
          break;

        case "send_media":
          if (sock) {
            await sock.sendMessage(msg.to, {
              [msg.media_type || "document"]: { url: msg.url },
              caption: msg.caption || "",
            });
          }
          break;

        case "status":
          sendToPython({ type: "status", data: connectionState });
          break;

        default:
          console.warn(`[sidecar] Unknown message type: ${msg.type}`);
      }
    } catch (err) {
      console.error("[sidecar] Error handling message:", err.message);
    }
  });

  ws.on("close", () => {
    console.log("[sidecar] Python adapter disconnected");
    pythonWs = null;
  });
});

// ==================== BAILEYS ====================

async function startBaileys() {
  console.log("[sidecar] Starting Baileys connection...");

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    printQRInTerminal: true, // also print to terminal for debugging
    logger,
    generateHighQualityLinkPreview: false,
  });

  // Connection state changes
  sock.ev.on("connection.update", (update) => {
    const { connection, qr, lastDisconnect } = update;

    if (qr) {
      console.log("[sidecar] QR code generated");
      sendToPython({ type: "qr", data: qr });
    }

    if (connection === "open") {
      const phone = sock.user?.id?.split(":")[0] || "unknown";
      connectionState = { connected: true, phone };
      console.log(`[sidecar] Connected as ${phone}`);
      sendToPython({ type: "connected", phone });
    }

    if (connection === "close") {
      connectionState = { connected: false, phone: null };
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const reason = DisconnectReason[statusCode] || `status_${statusCode}`;
      console.log(`[sidecar] Disconnected: ${reason}`);
      sendToPython({ type: "disconnected", reason });

      // Auto-reconnect unless logged out
      if (statusCode !== DisconnectReason.loggedOut) {
        console.log("[sidecar] Reconnecting in 5s...");
        setTimeout(startBaileys, 5000);
      } else {
        console.log("[sidecar] Logged out — manual reconnect required");
      }
    }
  });

  // Save auth credentials on update
  sock.ev.on("creds.update", saveCreds);

  // Incoming messages
  sock.ev.on("messages.upsert", ({ messages, type }) => {
    for (const msg of messages) {
      // Skip own messages and protocol messages
      if (msg.key.fromMe) continue;
      if (!msg.message) continue;

      // Extract text from various message types
      const text =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        msg.message.imageMessage?.caption ||
        msg.message.videoMessage?.caption ||
        msg.message.documentMessage?.caption ||
        "";

      // Detect media
      let media = null;
      if (msg.message.imageMessage) {
        media = { type: "image", mime: msg.message.imageMessage.mimetype };
      } else if (msg.message.audioMessage) {
        media = { type: "audio", mime: msg.message.audioMessage.mimetype };
      } else if (msg.message.videoMessage) {
        media = { type: "video", mime: msg.message.videoMessage.mimetype };
      } else if (msg.message.documentMessage) {
        media = {
          type: "document",
          mime: msg.message.documentMessage.mimetype,
          filename: msg.message.documentMessage.fileName,
        };
      }

      // Skip empty messages (reactions, read receipts, etc.)
      if (!text && !media) continue;

      sendToPython({
        type: "message",
        data: {
          id: msg.key.id,
          from: msg.key.remoteJid,
          participant: msg.key.participant || null,
          pushName: msg.pushName || "",
          text,
          media,
          timestamp: msg.messageTimestamp,
          isGroup: msg.key.remoteJid?.endsWith("@g.us") || false,
        },
      });
    }
  });
}

// ==================== HELPERS ====================

function sendToPython(data) {
  if (pythonWs && pythonWs.readyState === 1) {
    pythonWs.send(JSON.stringify(data));
  }
}

// Graceful shutdown
process.on("SIGINT", () => {
  console.log("[sidecar] Shutting down...");
  sock?.end();
  wss.close();
  process.exit(0);
});

process.on("SIGTERM", () => {
  console.log("[sidecar] SIGTERM received, shutting down...");
  sock?.end();
  wss.close();
  process.exit(0);
});
