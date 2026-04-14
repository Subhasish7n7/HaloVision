class VoiceScheduler {
  private queue: any[] = [];
  private speaking: boolean = false;

  speak(text: string, priority: number) {
    // 🚨 HIGH PRIORITY (interrupt)
    if (priority === 0) {
      speechSynthesis.cancel();
      this.queue = [];
      this.queue.push({ text, priority });
      this.process();
      return;
    }

    // ⚠️ MEDIUM PRIORITY (queue)
    if (priority === 1) {
      this.queue.push({ text, priority });
      this.process();
      return;
    }

    // ℹ️ LOW PRIORITY (skip if busy)
    if (priority >= 2) {
      if (this.speaking) return;
      this.queue.push({ text, priority });
      this.process();
    }
  }

  private process() {
    if (this.speaking) return;
    if (this.queue.length === 0) return;

    const item = this.queue.shift();
    if (!item) return;

    this.speaking = true;

    const utter = new SpeechSynthesisUtterance(item.text);

    // 🔥 optional styling
    if (item.priority === 0) {
      utter.rate = 1.2;
      utter.pitch = 1.3;
    }

    utter.onend = () => {
      this.speaking = false;
      this.process();
    };

    speechSynthesis.speak(utter);
  }
}

export const voiceScheduler = new VoiceScheduler();