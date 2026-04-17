# core/tts_engine.py

import asyncio
import logging

logger = logging.getLogger(__name__)

class TTSEngine:
    def __init__(self):
        try:
            import pyttsx3

            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", 180)
            self.engine.setProperty("volume", 1.0)

            logger.info("[TTS] Initialized")

        except Exception as e:
            logger.error(f"[TTS] Init failed: {e}")
            self.engine = None

    def _speak_blocking(self, text: str):
        """Runs inside thread (blocking safe)"""
        if not self.engine:
            return

        try:
            print(f"🔊 SPEAKING: {text}")
            self.engine.say(text)
            self.engine.runAndWait()

        except Exception as e:
            logger.error(f"[TTS] Speak error: {e}")

    async def speak(self, text: str):
        """Non-blocking call"""
        if not self.engine:
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._speak_blocking, text)


# 🔥 GLOBAL INSTANCE
tts_engine = TTSEngine()