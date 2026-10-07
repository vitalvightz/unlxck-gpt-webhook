/**
 * The guided visualisation's voice: the browser's own speech synthesis, slowed
 * down and pitched a touch lower so it reads as a calm corner voice rather than
 * a notification.
 *
 * Browsers only allow speech after a user gesture (iOS Safari is strict about
 * it), so `prime()` must be called synchronously inside the Begin tap. Every
 * line is short, which also sidesteps Chrome's habit of dropping long
 * utterances mid-sentence.
 */

/** Voices that sound least robotic, best first, matched on name. */
const PREFERRED_VOICE_HINTS = [
  "natural",
  "premium",
  "enhanced",
  "google uk english male",
  "daniel",
  "arthur",
  "google us english",
  "samantha",
];

function speech(): SpeechSynthesis | null {
  return typeof window !== "undefined" && "speechSynthesis" in window ? window.speechSynthesis : null;
}

export function speechAvailable(): boolean {
  return speech() !== null && typeof SpeechSynthesisUtterance !== "undefined";
}

export function pickVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const english = voices.filter((voice) => /^en([-_]|$)/i.test(voice.lang));
  if (english.length === 0) return null;
  for (const hint of PREFERRED_VOICE_HINTS) {
    const match = english.find((voice) => voice.name.toLowerCase().includes(hint));
    if (match) return match;
  }
  return english.find((voice) => voice.localService) ?? english[0];
}

let cachedVoice: SpeechSynthesisVoice | null | undefined;

function voice(): SpeechSynthesisVoice | null {
  const synth = speech();
  if (!synth) return null;
  if (cachedVoice === undefined) {
    const voices = synth.getVoices();
    if (voices.length === 0) {
      // Chrome loads voices asynchronously; use the default until they land.
      synth.addEventListener?.("voiceschanged", () => {
        cachedVoice = pickVoice(synth.getVoices());
      }, { once: true });
      return null;
    }
    cachedVoice = pickVoice(voices);
  }
  return cachedVoice;
}

/** Call inside the tap that starts playback, before any await. */
export function primeSpeech(): void {
  const synth = speech();
  if (!synth || typeof SpeechSynthesisUtterance === "undefined") return;
  try {
    voice();
    const primer = new SpeechSynthesisUtterance(" ");
    primer.volume = 0;
    synth.speak(primer);
  } catch {
    // Speech is optional: the player falls back to on-screen text.
  }
}

/**
 * Speak one line; `onDone` fires once when it ends, errors, or (as a guard for
 * engines that never fire `end`) after a generous timeout. Returns a cancel
 * function that stops the line without calling `onDone`.
 */
export function speakLine(
  text: string,
  options: { estimateSec: number; volume?: number },
  onDone: () => void,
): () => void {
  const synth = speech();
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    window.clearTimeout(guard);
    onDone();
  };
  const guard = window.setTimeout(finish, (options.estimateSec * 2.5 + 4) * 1000);
  if (!synth || typeof SpeechSynthesisUtterance === "undefined") {
    window.clearTimeout(guard);
    const fallback = window.setTimeout(finish, (options.estimateSec + 0.8) * 1000);
    return () => {
      finished = true;
      window.clearTimeout(fallback);
    };
  }
  try {
    synth.cancel();
    // A stuck paused engine (Chrome) swallows new lines until resumed.
    synth.resume();
    const utterance = new SpeechSynthesisUtterance(text);
    const chosen = voice();
    if (chosen) {
      utterance.voice = chosen;
      utterance.lang = chosen.lang;
    } else {
      utterance.lang = "en-GB";
    }
    utterance.rate = 0.88;
    utterance.pitch = 0.95;
    utterance.volume = options.volume ?? 1;
    utterance.onend = finish;
    utterance.onerror = finish;
    synth.speak(utterance);
  } catch {
    finish();
  }
  return () => {
    finished = true;
    window.clearTimeout(guard);
    try {
      synth.cancel();
    } catch {
      // Nothing to stop.
    }
  };
}

export function stopSpeech(): void {
  try {
    speech()?.cancel();
  } catch {
    // Nothing to stop.
  }
}
