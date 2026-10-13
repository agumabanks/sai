"""Whisper STT — transcribe audio files or WhatsApp voice notes to text."""
import os
import logging
import subprocess
import asyncio
import httpx
from core.skills.base import BaseSkill, SkillContext, SkillResult

logger = logging.getLogger(__name__)

VOICE_DOWNLOAD_DIR = "/tmp/sanaa_voice"


class WhisperSttSkill(BaseSkill):
    name = "whisper_stt"

    async def execute(self, args: dict, context: SkillContext) -> SkillResult:
        action = args.get("action", "transcribe")

        if action == "transcribe":
            audio_path = args.get("audio_path", "")
            model_choice = args.get("model", "api")
            if not audio_path or not os.path.exists(audio_path):
                return SkillResult(success=False, error=f"Audio file not found: {audio_path}")
            if model_choice == "api":
                return await self._transcribe_api(audio_path)
            return await self._transcribe_local(audio_path)

        elif action == "from_whatsapp_url":
            return await self._from_whatsapp_url(args)

        elif action == "from_url":
            return await self._from_url(args)

        return SkillResult(success=False, error=f"Unknown action: {action}")

    # ── transcribe via OpenAI Whisper API ────────────────────────────────────
    async def _transcribe_api(self, audio_path: str) -> SkillResult:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return await self._transcribe_local(audio_path)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                with open(audio_path, "rb") as f:
                    resp = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": (os.path.basename(audio_path), f, "audio/mpeg")},
                        data={"model": "whisper-1"},
                    )
                    resp.raise_for_status()
                    text = resp.json().get("text", "")
                    return SkillResult(success=True, output=text,
                                       data={"method": "openai_api", "chars": len(text)})
        except Exception as e:
            logger.warning(f"Whisper API failed: {e}, falling back to local.")
            return await self._transcribe_local(audio_path)

    # ── transcribe via local whisper CLI ─────────────────────────────────────
    async def _transcribe_local(self, audio_path: str) -> SkillResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "whisper", audio_path, "--model", "base",
                "--output_format", "txt", "--output_dir", "/tmp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

            if proc.returncode != 0:
                return SkillResult(success=False,
                                   error=f"Local whisper failed: {stderr.decode()[:300]}")

            txt_path = os.path.join("/tmp", os.path.splitext(os.path.basename(audio_path))[0] + ".txt")
            if os.path.exists(txt_path):
                with open(txt_path, "r") as f:
                    text = f.read().strip()
                return SkillResult(success=True, output=text,
                                   data={"method": "local_whisper", "chars": len(text)})

            return SkillResult(success=False, error="Whisper ran but no output file found.")
        except FileNotFoundError:
            return SkillResult(success=False,
                               error="Local whisper not installed. Run: pip install openai-whisper")
        except asyncio.TimeoutError:
            return SkillResult(success=False, error="Local whisper timed out after 3 minutes.")
        except Exception as e:
            return SkillResult(success=False, error=str(e))

    # ── download from a WhatsApp/generic URL then transcribe ─────────────────
    async def _from_url(self, args: dict) -> SkillResult:
        url = args.get("url", "").strip()
        model_choice = args.get("model", "api")
        if not url:
            return SkillResult(success=False, error="'url' is required.")

        os.makedirs(VOICE_DOWNLOAD_DIR, exist_ok=True)
        filename = os.path.join(VOICE_DOWNLOAD_DIR, f"voice_{abs(hash(url)) % 1000000}.ogg")

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "SanaaAI/1.0"})
                resp.raise_for_status()
                with open(filename, "wb") as f:
                    f.write(resp.content)
        except Exception as e:
            return SkillResult(success=False, error=f"Failed to download audio: {e}")

        if model_choice == "api":
            result = await self._transcribe_api(filename)
        else:
            result = await self._transcribe_local(filename)

        # Cleanup
        try:
            os.remove(filename)
        except Exception:
            pass

        return result

    # ── WhatsApp voice note pipeline (WhatsJet media URL) ────────────────────
    async def _from_whatsapp_url(self, args: dict) -> SkillResult:
        """Download a WhatsApp voice note via its media URL and transcribe it.

        Args:
            media_url  — WhatsApp media URL (from WhatsJet webhook payload)
            model      — 'api' or 'local'
        """
        media_url = args.get("media_url", "").strip()
        model_choice = args.get("model", "api")

        if not media_url:
            return SkillResult(success=False, error="'media_url' is required.")

        # WhatsJet media URLs may need a Bearer token
        try:
            from core.config import get_settings
            settings = get_settings()
            wa_key = getattr(settings, "whatsapp_api_key", "")
        except Exception:
            wa_key = ""

        os.makedirs(VOICE_DOWNLOAD_DIR, exist_ok=True)
        filename = os.path.join(VOICE_DOWNLOAD_DIR, f"wa_voice_{abs(hash(media_url)) % 1000000}.ogg")

        try:
            headers = {"User-Agent": "SanaaAI/1.0"}
            if wa_key:
                headers["Authorization"] = f"Bearer {wa_key}"

            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(media_url, headers=headers)
                resp.raise_for_status()
                with open(filename, "wb") as f:
                    f.write(resp.content)

            logger.info(f"Downloaded WA voice note: {len(resp.content)} bytes → {filename}")
        except Exception as e:
            return SkillResult(success=False, error=f"Failed to download WhatsApp voice note: {e}")

        # Transcribe
        if model_choice == "api":
            result = await self._transcribe_api(filename)
        else:
            result = await self._transcribe_local(filename)

        try:
            os.remove(filename)
        except Exception:
            pass

        return result
