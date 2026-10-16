import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_SOUND_SETTINGS } from "./audio";
import { addTime, advance, createTimerState, pause, resume, startItem } from "./engine";
import { MAX_ROUND_TRACK_MS, roundAudioTimeline, roundAudioWav } from "./round-audio";
import type { IntervalItem } from "./plan";

const item: IntervalItem = {
  kind: "interval", id: "rounds", title: "Rounds", detail: null,
  blockType: "sparring", rounds: 3, workSec: 180, restSec: 60,
  sparring: true, needsSetup: false,
};
const settings = DEFAULT_SOUND_SETTINGS;
const start = (overrides: Partial<IntervalItem> = {}, prepSec = 0) =>
  startItem(createTimerState([{ ...item, ...overrides }]), 1000, { prepSec }).state;

test("whole round/rest/prep schedule includes every bell and finishes without a final rest", () => {
  const track = roundAudioTimeline(start({}, 10), 1000, settings)!;
  assert.deepEqual(track.cues.filter((cue) => ["bell", "triple_bell", "finish"].includes(cue.sound)), [
    { atMs: 10_000, sound: "bell" },
    { atMs: 190_000, sound: "triple_bell" },
    { atMs: 250_000, sound: "bell" },
    { atMs: 430_000, sound: "triple_bell" },
    { atMs: 490_000, sound: "bell" },
    { atMs: 670_000, sound: "finish" },
  ]);
  assert.equal(track.durationMs, 674_000);
  assert.deepEqual(track.cues.filter((cue) => cue.sound === "clapper").map((cue) => cue.atMs), [180_000, 420_000, 660_000]);
});

test("warning preferences match engine rules, with one cue for coincident halfway/30 seconds", () => {
  const track = roundAudioTimeline(start({ rounds: 1, workSec: 60 }), 1000,
    { ...settings, warnThirty: true, warnHalfway: true, warnTen: false })!;
  assert.deepEqual(track.cues, [{ atMs: 30_000, sound: "double_beep" }, { atMs: 60_000, sound: "finish" }]);
});

test("restoring after suspension starts at the current round, never replays old cues", () => {
  const track = roundAudioTimeline(start(), 251_000, settings)!;
  assert.deepEqual(track.cues, [
    { atMs: 160_000, sound: "clapper" }, { atMs: 170_000, sound: "triple_bell" },
    { atMs: 230_000, sound: "bell" }, { atMs: 400_000, sound: "clapper" },
    { atMs: 410_000, sound: "finish" },
  ]);
  assert.equal(roundAudioTimeline(start(), 1_000_000, settings), null);
});

test("pause/resume and time edits rebuild deadlines without changing the round count", () => {
  const paused = pause(start(), 21_000);
  assert.equal(roundAudioTimeline(paused, 21_000, settings), null);
  const edited = addTime(resume(paused, 31_000), 10, 31_000);
  const track = roundAudioTimeline(edited, 31_000, settings)!;
  assert.equal(track.cues.find((cue) => cue.sound === "triple_bell")?.atMs, 170_000);
  assert.equal(track.cues.at(-1)?.atMs, 650_000);
});

test("track stops at an exercise boundary; zero-rest rounds match engine event precedence", () => {
  const state = startItem(createTimerState([{ ...item, rounds: 1 }, { ...item, id: "next" }]), 1000).state;
  assert.deepEqual(roundAudioTimeline(state, 1000, settings)!.cues.at(-1), { atMs: 180_000, sound: "triple_bell" });
  assert.deepEqual(roundAudioTimeline(start({ rounds: 2, restSec: 0, workSec: 5 }), 1000, settings)!.cues,
    [{ atMs: 5000, sound: "triple_bell" }, { atMs: 10_000, sound: "finish" }]);
});

test("unusually long schedules fail closed rather than allocate unbounded media", () => {
  assert.equal(roundAudioTimeline(start({ rounds: 30, workSec: MAX_ROUND_TRACK_MS / 1000 }), 1000, settings), null);
  assert.equal(roundAudioTimeline(createTimerState([item]), 1000, settings), null);
  assert.equal(advance(start(), 661_000).state.phase, "done");
});

test("WAV has correct size, format, silence, cue positions and overlapping clipped PCM", async () => {
  const wav = roundAudioWav({ durationMs: 2000, cues: [
    { atMs: 1000, sound: "bell" }, { atMs: 1000, sound: "clapper" },
  ] }, new Map([["bell", new Float32Array([0.75, -0.75])], ["clapper", new Float32Array([0.75, -0.75])]]));
  const bytes = await wav.arrayBuffer();
  const data = new DataView(bytes);
  assert.equal(wav.type, "audio/wav");
  assert.equal(bytes.byteLength, 44 + 2000 * 16 * 2);
  assert.equal(new TextDecoder().decode(bytes.slice(0, 4)), "RIFF");
  assert.equal(data.getUint32(24, true), 16000);
  assert.equal(data.getUint16(34, true), 16);
  assert.equal(data.getUint32(40, true), bytes.byteLength - 44);
  assert.equal(data.getInt16(44 + 15999 * 2, true), 0);
  assert.equal(data.getInt16(44 + 16000 * 2, true), 32767);
  assert.equal(data.getInt16(44 + 16001 * 2, true), -32767);
  assert.equal(data.getInt16(44 + 16002 * 2, true), 0);
  const quieter = new DataView(await roundAudioWav({ durationMs: 1000, cues: [{ atMs: 0, sound: "bell" }] },
    new Map([["bell", new Float32Array([1])]]), 0.25).arrayBuffer());
  assert.equal(quieter.getInt16(44, true), 8192, "volume must be encoded for iOS, which ignores media.volume");
});
