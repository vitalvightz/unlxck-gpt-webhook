import test from "node:test";
import assert from "node:assert/strict";

import {
  demoFullVideoUrl,
  demoSegmentLabel,
  demoThumbnailUrl,
  hasWatchedDemo,
  loadYouTubeIframeApi,
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

test("a failed player load is retried on the next tap and restores the global hook", async () => {
  type FakeScript = { src?: string; async?: boolean; onerror?: () => void; remove: () => void };
  const scripts: FakeScript[] = [];
  const originalHook = () => {};
  const globals = globalThis as unknown as { window?: unknown; document?: unknown };
  const previousWindow = globals.window;
  const previousDocument = globals.document;
  const fakeWindow: Record<string, unknown> = {
    onYouTubeIframeAPIReady: originalHook,
    setTimeout: () => 1,
    clearTimeout: () => {},
  };
  globals.window = fakeWindow;
  globals.document = {
    createElement: () => {
      const script: FakeScript = { remove: () => {} };
      scripts.push(script);
      return script;
    },
    head: { appendChild: () => {} },
  };
  try {
    // The API script loads but YT never appears: reject, and do not cache it.
    const first = loadYouTubeIframeApi();
    (fakeWindow.onYouTubeIframeAPIReady as () => void)();
    await assert.rejects(first, /failed to load/);
    assert.equal(fakeWindow.onYouTubeIframeAPIReady, originalHook);

    // The next tap starts a fresh load instead of reusing the rejection.
    const second = loadYouTubeIframeApi();
    assert.equal(scripts.length, 2);
    scripts[1]!.onerror?.();
    await assert.rejects(second, /failed to load/);
    assert.equal(fakeWindow.onYouTubeIframeAPIReady, originalHook);
  } finally {
    globals.window = previousWindow;
    globals.document = previousDocument;
  }
});
