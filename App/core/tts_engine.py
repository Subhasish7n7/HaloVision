# core/tts_engine.py

import asyncio
import edge_tts
import pygame
import tempfile
import os
import logging

logger = logging.getLogger(__name__)


class TTSEngine:
    def __init__(self):
        self.voice = "en-US-AriaNeural"
        self.queue = asyncio.Queue()
        self.worker_started = False

        try:
            pygame.mixer.init()
            logger.info("Edge TTS initialized")
        except Exception as e:
            logger.exception(f"TTS init failed: {e}")

    async def start(self):
        if self.worker_started:
            return

        self.worker_started = True
        asyncio.create_task(self._speech_worker())
        logger.info("TTS worker started")

    async def speak(self, text: str):
        if not text:
            return

        try:
            await self.queue.put(text)
        except Exception as e:
            logger.exception(f"Queue error: {e}")

    async def _speech_worker(self):
        while True:
            text = await self.queue.get()
            temp_file = None

            try:
                logger.info(f"Speaking: {text[:60]}")

                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                    temp_file = f.name

                communicate = edge_tts.Communicate(text=text, voice=self.voice)
                await communicate.save(temp_file)

                pygame.mixer.music.stop()
                pygame.mixer.music.load(temp_file)
                pygame.mixer.music.play()

                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.05)

                logger.debug("Speech finished")

            except Exception as e:
                logger.exception(f"Speech error: {e}")

            finally:
                try:
                    if temp_file and os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception:
                    pass

                self.queue.task_done()


tts_engine = TTSEngine()
