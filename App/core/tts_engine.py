# core/tts_engine.py
import asyncio
import logging
import base64
import io

logger = logging.getLogger(__name__)

# ============================================================
# 🔧 TOGGLE (IMPORTANT)
# ============================================================

ENABLE_TTS = True  # ❌ KEEP FALSE ON WORK LAPTOP
# Set to True on your RTX machine


class TTSEngine:
    def __init__(self):
        self.enabled = ENABLE_TTS
        self.tts = None

        if self.enabled:
            try:
                from TTS.api import TTS
                self.tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")
                logger.info("[TTS] Model loaded successfully")
            except Exception as e:
                logger.error(f"[TTS] Failed to load model: {e}")
                self.enabled = False
        else:
            logger.info("[TTS] Running in DISABLED mode")

    async def synthesize(self, text: str) -> str:

        if not self.enabled:
            logger.info(f"[TTS MOCK] {text}")
            return ""

        try:
            loop = asyncio.get_running_loop()

            # 🔹 Run TTS model (blocking → thread)
            wav_bytes = await loop.run_in_executor(
                None,
                self.tts.tts,
                text
            )

            # 🔹 Run audio encoding (also blocking → thread)
            def encode_audio():
                buffer = io.BytesIO()
                import soundfile as sf
                sf.write(buffer, wav_bytes, samplerate=22050, format="WAV")
                return base64.b64encode(buffer.getvalue()).decode("utf-8")

            audio_base64 = await loop.run_in_executor(
                None,
                encode_audio
            )

            logger.info(f"[TTS] Generated audio for: {text}")

            return audio_base64

        except Exception as e:
            logger.error(f"[TTS] Error generating speech: {e}")
            return ""