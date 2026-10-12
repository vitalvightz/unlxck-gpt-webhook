import test from "node:test";
import assert from "node:assert/strict";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { PrivateExerciseMediaProvider } from "./private-exercise-video";
import { ExerciseRow } from "./structured-plan-renderer";
import type { PrivateMediaPreview } from "@/lib/api-schema.generated";
import type { StructuredBlock } from "@/lib/types";

const block: StructuredBlock = { block_id: "curl", display_name: "My curl", block_type: "accessory",
  prescription_source: "athlete", private_media_id: "private-clip", athlete_dose: { mode: "reps", sets: 3, reps: 12 } };
const clip: PrivateMediaPreview = { id: "private-clip", provider: "youtube", video_id: "dQw4w9WgXcQ", asset_id: null,
  start_s: 12, end_s: 28, channel_title: "Coach", orientation: "landscape", url: null };

async function fixture(response: (url: string) => unknown = () => clip) {
  const original = globalThis.fetch;
  const requests: { url: string; token: string | null }[] = [];
  globalThis.fetch = (async (input, init) => {
    requests.push({ url: String(input), token: new Headers(init?.headers).get("Authorization") });
    return new Response(JSON.stringify(response(String(input))));
  }) as typeof fetch;
  const host = document.createElement("div"); document.body.append(host);
  const root = createRoot(host);
  const render = async (open = false, token: string | null = "owner-token", value = block) => {
    await act(async () => root.render(<PrivateExerciseMediaProvider token={token}>
      <ExerciseRow block={value} open={open} onToggle={() => {}} />
    </PrivateExerciseMediaProvider>));
  };
  return { host, requests, render, cleanup: async () => {
    await act(async () => root.unmount()); host.remove(); globalThis.fetch = original;
  } };
}

test("attached clip appears on the collapsed row and shares its authenticated read with the expanded player", async () => {
  const view = await fixture();
  try {
    await view.render();
    assert.match(view.host.querySelector<HTMLImageElement>(".ex-row-thumb img")!.src, /mqdefault.jpg$/);
    assert.match(view.host.textContent!, /Has demo video/);
    assert.equal(view.host.querySelectorAll("iframe").length, 0);
    assert.equal(view.requests[0].token, "Bearer owner-token");
    await view.render(true);
    assert.ok(view.host.querySelector(".ex-demo-frame img"));
    assert.equal(view.requests.length, 1);
    await view.render(false, null);
    assert.equal(view.host.querySelector(".ex-row-thumb"), null);
    await view.render(false, "different-owner-token");
    assert.equal(view.requests.length, 2);
    assert.equal(view.requests[1].token, "Bearer different-owner-token");
  } finally { await view.cleanup(); }
});

test("community clips resolve through the revision endpoint before opening", async () => {
  const view = await fixture(() => ({ media: clip }));
  try {
    await view.render(false, "owner-token", { ...block, private_media_id: null, community_revision_id: "revision" });
    assert.ok(view.host.querySelector(".ex-row-thumb img"));
    assert.match(view.requests[0].url, /community-exercises\/revisions\/revision/);
  } finally { await view.cleanup(); }
});

test("uploaded preview uses a muted static video frame and refreshes expired signed URLs on reopen", async () => {
  const view = await fixture(() => ({ ...clip, provider: "uploaded", video_id: null, url: "https://signed.example/video.mp4" }));
  const now = Date.now;
  try {
    await view.render();
    const video = view.host.querySelector<HTMLVideoElement>(".ex-row-thumb video")!;
    assert.equal(video.preload, "metadata"); assert.equal(video.muted, true); assert.equal(video.autoplay, false);
    Date.now = () => now() + 46_000;
    await view.render(true);
    assert.equal(view.requests.length, 2);
  } finally { Date.now = now; await view.cleanup(); }
});
