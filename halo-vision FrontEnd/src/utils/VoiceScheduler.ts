class VoiceScheduler {
  private queue: any[] = [];
  private speaking = false;

  speak(text: string, priority: number, direction?: string) {
    // 🔥 Direction enhancement
    let finalText = text;

    if (direction === "left") finalText = "Left side " + text;
    if (direction === "right") finalText = "Right side " + text;

    // 🔥 PRIORITY SYSTEM
    if (priority === 0) {
      speechSynthesis.cancel();
      this.queue = [];
    }

    this.queue.push({ text: finalText, priority });
    this.process();
  }

  private process() {
    if (this.speaking || this.queue.length === 0) return;

    const item = this.queue.shift();
    this.speaking = true;

    const utter = new SpeechSynthesisUtterance(item.text);

    // 🔥 STYLE BY PRIORITY
    if (item.priority === 0) {
      utter.rate = 1.3;
      utter.pitch = 1.4;
    } else if (item.priority === 1) {
      utter.rate = 1.1;
    } else {
      utter.rate = 0.9;
    }

    utter.onend = () => {
      this.speaking = false;
      this.process();
    };

    speechSynthesis.speak(utter);
  }
}

export const voiceScheduler = new VoiceScheduler();