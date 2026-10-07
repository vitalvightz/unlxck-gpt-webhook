/**
 * The crowd under a guided visualisation: a looping fight-night ambience that
 * matches the athlete's level, so the imagined room sounds like the real one
 * (the Environment part of PETTLEP).
 *
 * Amateur: a small hall, scattered voices, corner shouts. Professional: an
 * arena roar. The loops are CC0 recordings served from /audio (see
 * public/audio/README.md); when a file is missing the crowd is simply off.
 *
 * Played through Web Audio rather than an <audio> element: buffer looping is
 * seamless, and iOS ignores `HTMLMediaElement.volume`, so ducking needs a gain
 * node.
 */

export type FightLevel = "amateur" | "professional";

export const CROWD_SOURCES: Record<FightLevel, string> = {
  amateur: "/audio/crowd-amateur.mp3",
  professional: "/audio/crowd-professional.mp3",
};

/** The athlete's profile value onto a crowd; unknown reads as amateur. */
export function fightLevel(value: string | null | undefined): FightLevel {
  return (value ?? "").trim().toLowerCase().startsWith("pro") ? "professional" : "amateur";
}

/** Crowd level for a moment of the session, before the master volume. */
export function crowdLevel(options: {
  phase: "settle" | "frame" | "rehearse" | "anchor" | "close" | "done";
  speaking: boolean;
  /** D-1 / D-0: familiar and calm, so the crowd stays well back. */
  calm: boolean;
}): number {
  const base =
    options.phase === "rehearse" ? 0.55 : options.phase === "frame" || options.phase === "anchor" ? 0.3 : 0;
  // The voice always sits on top: duck the crowd while a line is spoken.
  const ducked = options.speaking ? base * 0.4 : base;
  return options.calm ? ducked * 0.5 : ducked;
}

type WebkitWindow = Window & { webkitAudioContext?: typeof AudioContext };

const MP3_PADDING_SEC = 0.06;

export class CrowdBed {
  private context: AudioContext | null = null;
  private gain: GainNode | null = null;
  private source: AudioBufferSourceNode | null = null;
  private buffer: AudioBuffer | null = null;
  private loading: Promise<boolean> | null = null;

  constructor(private readonly url: string) {}

  /** Call inside a tap: creates and resumes the audio context. */
  unlock(): void {
    if (typeof window === "undefined") return;
    if (!this.context) {
      const Context = window.AudioContext ?? (window as WebkitWindow).webkitAudioContext;
      if (!Context) return;
      this.context = new Context();
      this.gain = this.context.createGain();
      this.gain.gain.value = 0;
      this.gain.connect(this.context.destination);
    }
    if (this.context.state === "suspended") void this.context.resume();
  }

  /** Fetch and decode the loop; resolves false when it is unavailable. */
  load(): Promise<boolean> {
    this.loading ??= (async () => {
      try {
        const response = await fetch(this.url);
        if (!response.ok) return false;
        const data = await response.arrayBuffer();
        this.unlock();
        if (!this.context) return false;
        this.buffer = await this.context.decodeAudioData(data);
        return true;
      } catch {
        return false;
      }
    })();
    return this.loading;
  }

  /** Start the loop (silent until `fadeTo`). Safe to call repeatedly. */
  start(): void {
    if (!this.context || !this.gain || !this.buffer || this.source) return;
    const source = this.context.createBufferSource();
    source.buffer = this.buffer;
    source.loop = true;
    // MP3 encoders pad a few ms of silence at each end; loop inside it so the
    // bed never drops out at the seam.
    if (this.buffer.duration > 1) {
      source.loopStart = MP3_PADDING_SEC;
      source.loopEnd = this.buffer.duration - MP3_PADDING_SEC;
    }
    source.connect(this.gain);
    source.start();
    this.source = source;
  }

  /** Glide to `level` (0..1) over `seconds`. */
  fadeTo(level: number, seconds = 1.5): void {
    if (!this.context || !this.gain) return;
    const now = this.context.currentTime;
    const param = this.gain.gain;
    param.cancelScheduledValues(now);
    param.setValueAtTime(param.value, now);
    param.linearRampToValueAtTime(Math.max(0, Math.min(1, level)), now + Math.max(0.05, seconds));
  }

  stop(): void {
    try {
      this.source?.stop();
    } catch {
      // Already stopped.
    }
    this.source?.disconnect();
    this.source = null;
    if (this.gain && this.context) this.gain.gain.setValueAtTime(0, this.context.currentTime);
  }

  close(): void {
    this.stop();
    void this.context?.close().catch(() => undefined);
    this.context = null;
    this.gain = null;
  }
}
