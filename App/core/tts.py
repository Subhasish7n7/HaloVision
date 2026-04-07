import pyttsx3
import threading
import queue


class TTS:
    def __init__(self):
        self.engine = pyttsx3.init()

        self.queue = queue.Queue()
        self.lock = threading.Lock()

        # 🔥 single worker thread
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    # ============================================================
    # PUBLIC SPEAK
    # ============================================================

    def speak(self, text):
        if not text:
            return

        # enqueue instead of spawning threads
        self.queue.put(text)

    # ============================================================
    # INTERNAL WORKER (ONLY ONE SPEAKER)
    # ============================================================

    def _run(self):
        while True:
            text = self.queue.get()

            try:
                with self.lock:
                    self.engine.say(text)
                    self.engine.runAndWait()

            except Exception as e:
                print(f"TTS Error: {e}")

            self.queue.task_done()


# global instance
tts = TTS()