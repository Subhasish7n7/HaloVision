import asyncio
import logging
import base64
import io
import tempfile
import os

logger = logging.getLogger(__name__)

# ============================================================
# 🔧 TOGGLE
# ============================================================

ENABLE_TTS = True  # ✅ now works locally


class TTSEngine:
    def __init__(self):
        self.enabled = ENABLE_TTS
        self.engine = None

        if self.enabled:
            try:
                import pyttsx3

                self.engine = pyttsx3.init()
                self.engine.setProperty('rate', 180)
                self.engine.setProperty('volume', 1.0)

                logger.info("[TTS] pyttsx3 initialized")

            except Exception as e:
                logger.error(f"[TTS] Failed to init pyttsx3: {e}")
                self.enabled = False
        else:
            logger.info("[TTS] Running in DISABLED mode")

    async def synthesize(self, text: str) -> str:

        if not self.enabled:
            logger.info(f"[TTS MOCK] {text}")
            return ""

        try:
            loop = asyncio.get_running_loop()

            def generate_audio():
                # 🔥 Create temp file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                    filename = tmp.name

                # 🔊 Generate speech
                self.engine.save_to_file(text, filename)
                self.engine.runAndWait()

                # 📦 Read and encode
                with open(filename, "rb") as f:
                    audio_bytes = f.read()

                # 🧹 Cleanup
                os.remove(filename)

                return base64.b64encode(audio_bytes).decode("utf-8")

            # 🔥 Run in thread (non-blocking)
            audio_base64 = await loop.run_in_executor(
                None,
                generate_audio
            )

            logger.info(f"[TTS] Generated audio for: {text}")

            return audio_base64

        except Exception as e:
            logger.error(f"[TTS] Error generating speech: {e}")
            return ""