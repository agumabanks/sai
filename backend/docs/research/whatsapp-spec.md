# 📱 ANTIGRAVITY — WhatsApp Integration Specification

## 1. OBJECTIVE
Implement a robust, persistent WhatsApp integration for Antigravity using the [Baileys](https://github.com/WhiskeySockets/Baileys) pattern (translated to Python logic where applicable, or using a Node.js sidecar/node).

---

## 2. CORE ARCHITECTURE

### 2.1 Sidecar vs. Native logic
OpenClaw uses Node.js (TypeScript) and Baileys directly. For Antigravity (Python), we propose a **WhatsApp Node** (Node.js sidecar) that communicates with-Antigravity via WebSocket or a local IPC (Inter-Process Communication).

---

## 3. TECHNICAL SPECIFICATION (PYTHON STUBS)

### 3.1 Session Manager
Responsible for maintaining the "auth" state on disk and handling the lifecycle of the connection.

```python
class WhatsAppSession:
    def __init__(self, session_id: str, auth_dir: str):
        self.session_id = session_id
        self.auth_dir = auth_dir
        self.status = "disconnected" # disconnected, connecting, open, pairing

    def is_linked(self) -> bool:
        """Checks if auth files exist and are valid."""
        pass

    def start_pairing(self):
        """Triggers the QR generation flow."""
        pass

    def on_qr_received(self, qr_code: str):
        """Callback to display/emit the QR code."""
        pass

    def logout(self):
        """Clears auth files and disconnects."""
        pass
```

### 3.2 Message Interceptor
Listens for incoming events and transforms them into Antigravity's internal `Message` format.

```python
class WhatsAppInboundHandler:
    async def handle_message_upsert(self, raw_msg: dict):
        """
        Parses Baileys 'messages.upsert' event.
        Logic:
        1. Ignore status/broadcast updates.
        2. Deduplicate using (session_id, remote_jid, message_id).
        3. Extract text, mentions, and media placeholders.
        4. Trigger Antigravity Router.
        """
        pass

    def deduplicate(self, msg_id: str) -> bool:
        """Checks Redis/SQLite to see if this ID was recently processed."""
        pass

    async def download_media(self, media_key: str, media_type: str) -> str:
        """Downloads and saves media to the storage bucket."""
        pass
```

### 3.3 Outbound Adapter
Sends messages, reactions, and provides presence updates.

```python
class WhatsAppOutboundAdapter:
    async def send_text(self, to: str, text: str):
        """Sends a plain text message."""
        pass

    async def send_media(self, to: str, media_url: str, caption: str = ""):
        """Sends image/video/audio with an optional caption."""
        pass

    async def send_reaction(self, chat_id: str, message_id: str, emoji: str):
        """Sends a reaction to a specific message."""
        pass

    async def set_typing(self, chat_id: str, active: bool):
        """Updates presence status (composing/available)."""
        pass
```

---

## 4. FLOWS

### 4.1 QR Pairing Flow
1. **Initialize**: Sidecar starts a Baileys socket using `useMultiFileAuthState`.
2. **Event**: Listen for `connection.update`.
3. **QR**: If `qr` property is present, emit to Antigravity.
4. **Display**: Antigravity prints QR to terminal or sends to User UI.
5. **Open**: Once `connection === "open"`, session is marked as `linked`.

### 4.2 Message Interception & Deduplication
- **Key Discovery**: Baileys provides a unique `id` for every message.
- **Dedupe**: Antigravity should use a 24-hour TTL in Redis/Postgres for message IDs to avoid double-processing during re-synchronization.
- **Mentions**: Baileys provides `mentionedJid` array. We must map these to internal User IDs.

### 4.3 Persistence
- **Storage**: Store the `auth-dir` (JSON files) in a persistent volume.
- **Encryption**: Sensitive credentials in `creds.json` should be ideally encrypted at rest.

---

## 5. SECURITY CONSIDERATIONS
- **Credential Protection**: The `auth-dir` contains full access tokens for the WhatsApp account. It must be protected with `0600` permissions.
- **Origin Validation**: If the sidecar is remote, enforce strict TLS and Token-based auth between Antigravity and the Sidecar.
