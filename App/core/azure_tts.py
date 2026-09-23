import os
import asyncio
import tempfile
import logging
import platform
import threading

logger = logging.getLogger(__name__)

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False


class AzureTTS:
    def __init__(self):
        self._voice = os.getenv("AZURE_SPEECH_VOICE", "en-US-AriaNeural")
        self._initialized = False
        self._local_engine = None
        self._edge_failed = False

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True

        if EDGE_TTS_AVAILABLE and not self._edge_failed:
            self._initialized = True
            logger.info(f"[TTS] Initialized with edge-tts (voice={self._voice})")
            return True

        if PYTTSX3_AVAILABLE:
            try:
                self._local_engine = pyttsx3.init()
                self._local_engine.setProperty("rate", 160)
                self._initialized = True
                logger.info("[TTS] Initialized with local pyttsx3 (SAPI5)")
                return True
            except Exception as e:
                logger.warning(f"[TTS] pyttsx3 init failed: {e}")

        logger.error("[TTS] No TTS engine available (neither edge-tts nor pyttsx3)")
        return False

    async def speak(self, text: str) -> bool:
        if not text or not text.strip():
            return False

        if not self._ensure_initialized():
            return False

        if EDGE_TTS_AVAILABLE and not self._edge_failed:
            try:
                return await self._speak_edge(text)
            except Exception as e:
                logger.warning(f"[TTS] edge-tts failed ({e}), switching to local TTS")
                self._edge_failed = True

        if PYTTSX3_AVAILABLE:
            if not self._local_engine:
                try:
                    self._local_engine = pyttsx3.init()
                    self._local_engine.setProperty("rate", 160)
                except Exception as e:
                    logger.error(f"[TTS] pyttsx3 init failed: {e}")
                    return False
            try:
                return await self._speak_local(text)
            except Exception as e:
                logger.error(f"[TTS] Local TTS also failed: {e}")

        return False

    async def _speak_edge(self, text: str) -> bool:
        communicate = edge_tts.Communicate(text=text, voice=self._voice)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            temp_path = f.name

        try:
            await communicate.save(temp_path)
            logger.info(f"[TTS] edge-tts synthesized: {text[:80]}")

            if platform.system() == "Windows":
                ps_cmd = (
                    "Add-Type -AssemblyName PresentationCore; "
                    f"$p = New-Object System.Windows.Media.MediaPlayer; "
                    f"$p.Open([uri]::new('file:///{temp_path}')); "
                    f"$p.Play(); "
                    f"Start-Sleep -Milliseconds 500; "
                    f"while ($p.Position -lt $p.NaturalDuration.TimeSpan) "
                    f"{{ Start-Sleep -Milliseconds 200 }}; "
                    f"$p.Close()"
                )
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-NoProfile", "-Command", ps_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
            else:
                proc = await asyncio.create_subprocess_exec(
                    "mpg123", "-q", temp_path,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()

            logger.info(f"[TTS] edge-tts played: {text[:60]}")
            return True
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    async def _speak_local(self, text: str) -> bool:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._local_engine.say, text)
        await loop.run_in_executor(None, self._local_engine.runAndWait)
        logger.info(f"[TTS] Local SAPI5 played: {text[:60]}")
        return True


azure_tts = AzureTTS()
