import test from "node:test";
import assert from "node:assert/strict";

import {
  demoFullVideoUrl,
  demoSegmentLabel,
  demoThumbnailUrl,
  hasWatchedDemo,
  markDemoWatched,
} from "./exercise-demo";
import type { ExerciseMedia } from "./types";

const media: ExerciseMedia = {
  provider: "youtube",
  video_id: "dQw4w9WgXcQ",
  start_s: 42,
  end_s: 70,
  source: "curated",
};

test("segment label reads as a clock range, or an open start", () => {
  assert.equal(demoSegmentLabel(media), "0:42–1:10");
  assert.equal(demoSegmentLabel({ ...media, end_s: null }), "from 0:42");
  assert.equal(demoSegmentLabel({ ...media, start_s: 0, end_s: null }), null);
  assert.equal(demoSegmentLabel({ ...media, start_s: 30, end_s: 10 }), "from 0:30");
});

test("full video link opens YouTube at the demo segment", () => {
  assert.equal(demoFullVideoUrl(media), "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s");
  assert.equal(
    demoFullVideoUrl({ ...media, start_s: 0 }),
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  );
});

test("thumbnail URL uses the YouTube image host", () => {
  assert.equal(demoThumbnailUrl("dQw4w9WgXcQ", "mq"), "https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg");
});

test("watched memory is per video and survives unavailable storage", () => {
  const store = new Map<string, string>();
  const globals = globalThis as unknown as { window?: unknown };
  const previous = globals.window;
  globals.window = {
    localStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
    },
  };
  try {
    assert.equal(hasWatchedDemo("dQw4w9WgXcQ"), false);
    markDemoWatched("dQw4w9WgXcQ");
    assert.equal(hasWatchedDemo("dQw4w9WgXcQ"), true);
    assert.equal(hasWatchedDemo("AAAAAAAAAAA"), false);

    globals.window = {
      localStorage: {
        getItem: () => {
          throw new Error("blocked");
        },
        setItem: () => {
          throw new Error("blocked");
        },
      },
    };
    assert.equal(hasWatchedDemo("dQw4w9WgXcQ"), false);
    assert.doesNotThrow(() => markDemoWatched("dQw4w9WgXcQ"));
  } finally {
    globals.window = previous;
  }
});
