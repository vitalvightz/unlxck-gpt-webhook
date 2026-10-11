"use client";

import { useEffect, useRef, useState } from "react";
import {
  createPrivateYouTubeClip, getPrivateMedia, getPrivateMediaSettings, getPrivateUpload, reservePrivateUpload,
} from "@/lib/api";
import type { PrivateMediaPreview, PrivateMediaSettings } from "@/lib/api-schema.generated";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { ExerciseDemo } from "./exercise-demo";
import { InjuryDetailSheet } from "./today/injury-detail-sheet";
import styles from "./custom-plan-builder.module.css";
import layout from "./private-exercise-video.module.css";

export function PrivateVideoPlayer({ media, name }: { media: PrivateMediaPreview; name: string }) {
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false), [slow, setSlow] = useState(false);
  const [failed, setFailed] = useState(false);
  if (media.provider === "youtube" && media.video_id) return (
    <ExerciseDemo key={`${media.video_id}:${media.start_s}:${media.end_s}`} exerciseName={name} preview media={{
      provider: "youtube", video_id: media.video_id, start_s: media.start_s, end_s: media.end_s,
      channel_title: media.channel_title, orientation: media.orientation, source: "curated",
    }} />
  );
  if (!media.url || failed) return <p role="status">Video unavailable. Reopen the preview to try again.</p>;
  return (
    <div className="ex-demo" data-orientation={media.orientation === "portrait" ? "portrait" : undefined}>
      <div className="ex-demo-frame">
        <video ref={video} className="ex-demo-player" src={media.url} playsInline muted loop preload="metadata"
          aria-label={`${name} demonstration`} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
          onError={() => setFailed(true)} />
      </div>
      <div className="ex-demo-caption"><span className="ex-demo-meta">Demo · Private</span></div>
      <div className="ex-demo-controls" role="group" aria-label="Demo controls">
        <button type="button" className="ex-demo-control" onClick={() => {
          if (playing) video.current?.pause(); else void video.current?.play().catch(() => setFailed(true));
        }}>{playing ? "Pause" : "Play"}</button>
        <button type="button" className="ex-demo-control" onClick={() => {
          if (video.current) { video.current.currentTime = 0; void video.current.play().catch(() => setFailed(true)); }
        }}>Replay</button>
        <button type="button" className="ex-demo-control" aria-pressed={slow} onClick={() => {
          if (video.current) video.current.playbackRate = slow ? 1 : 0.5;
          setSlow(!slow);
        }}>0.5×</button>
      </div>
      {/* Renditions intentionally strip audio and all embedded metadata. */}
    </div>
  );
}

export function PrivateExerciseVideo({ token, id, name }: { token: string; id: string; name: string }) {
  const [loaded, setLoaded] = useState<{ token: string; id: string; media?: PrivateMediaPreview; error?: boolean }>();
  const media = loaded?.token === token && loaded.id === id ? loaded.media : undefined;
  const error = loaded?.token === token && loaded.id === id && loaded.error;
  useEffect(() => {
    const request = new AbortController();
    void getPrivateMedia(token, id, request.signal).then(media => {
      if (!request.signal.aborted) setLoaded({ token, id, media });
    }).catch(() => { if (!request.signal.aborted) setLoaded({ token, id, error: true }); });
    return () => request.abort();
  }, [token, id]);
  return <div className={layout.preview}>{media ? <PrivateVideoPlayer key={media.url ?? media.id} media={media} name={name} />
    : <p role="status">{error ? "Video unavailable. You can keep using your exercise." : "Opening video…"}</p>}</div>;
}

export function PrivateExerciseVideoSheet({ token, name, onClose, onAttach }: {
  token: string; name: string; onClose: () => void; onAttach: (id: string) => void;
}) {
  const [settings, setSettings] = useState<PrivateMediaSettings>();
  const [choice, setChoice] = useState<"upload" | "youtube">();
  const [url, setUrl] = useState(""), [start, setStart] = useState("0"), [end, setEnd] = useState("30");
  const [media, setMedia] = useState<PrivateMediaPreview>(), [pending, setPending] = useState(false);
  const [error, setError] = useState<string>(), [status, setStatus] = useState<string>();
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void getPrivateMediaSettings(token, controller.signal).then(setSettings)
      .catch(() => { if (!controller.signal.aborted) setError("Video options are temporarily unavailable."); });
    return () => { controller.abort(); request.current?.abort(); };
  }, [token]);
  function changed() { setMedia(undefined); setError(undefined); }
  async function verifyYouTube(event: React.FormEvent) {
    event.preventDefault();
    changed();
    const start_s = Number(start), end_s = Number(end);
    if (!start.trim() || !end.trim() || !Number.isInteger(start_s) || !Number.isInteger(end_s) || start_s < 0 || end_s <= start_s || end_s - start_s > 30) {
      setError("Choose a clip between 1 and 30 seconds."); return;
    }
    setPending(true);
    request.current = new AbortController();
    try { setMedia(await createPrivateYouTubeClip(token, { url, start_s, end_s }, request.current.signal)); }
    catch (reason) { if (!request.current.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to preview video."); }
    finally { setPending(false); }
  }
  async function upload(file?: File) {
    if (!file) return;
    changed();
    if (file.size > 20 * 1024 * 1024 || !["video/mp4", "video/quicktime", "video/webm"].includes(file.type)) {
      setError("Choose an MP4, MOV or WebM video under 20 MB and 30 seconds."); return;
    }
    const controller = new AbortController(); request.current = controller;
    setPending(true); setStatus("Uploading video…");
    try {
      const permission = await reservePrivateUpload(token, file, controller.signal);
      const result = await getSupabaseBrowserClient().storage.from(permission.bucket).upload(permission.path, file, { contentType: file.type, upsert: false });
      if (result.error) throw new Error("Unable to upload video. Try again.");
      setStatus("Checking video…");
      const deadline = Date.now() + 5 * 60 * 1000;
      while (!controller.signal.aborted && Date.now() < deadline) {
        const result = await getPrivateUpload(token, permission.asset_id, controller.signal);
        if (result.status === "verified" && result.media) { setMedia(result.media); return; }
        if (result.status === "rejected" || result.status === "deleted") throw new Error("Video could not be accepted. Choose a video under 30 seconds.");
        await new Promise<void>((resolve) => {
          const done = () => { clearTimeout(timer); controller.signal.removeEventListener("abort", done); resolve(); };
          const timer = setTimeout(done, 2500); controller.signal.addEventListener("abort", done, { once: true });
        });
      }
      if (!controller.signal.aborted) throw new Error("Video is taking longer than expected. Try again later.");
    } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to upload video."); }
    finally { if (!controller.signal.aborted) { setPending(false); setStatus(undefined); } }
  }
  const clipForm = <form onSubmit={(e) => void verifyYouTube(e)} className={layout.form}>
    <fieldset disabled={pending} className={layout.form}>
      <label><span>YouTube link</span><input type="url" required value={url} maxLength={500} onChange={(e) => { setUrl(e.target.value); changed(); }} /></label>
      <div className={layout.times}>
        <label><span>Start (seconds)</span><input inputMode="numeric" type="number" min={0} max={86400} required value={start} onChange={(e) => { setStart(e.target.value); changed(); }} /></label>
        <label><span>End (seconds)</span><input inputMode="numeric" type="number" min={1} max={86430} required value={end} onChange={(e) => { setEnd(e.target.value); changed(); }} /></label>
      </div>
      <button className="secondary-button" type="submit">{pending ? "Checking…" : "Preview clip"}</button>
    </fieldset>
  </form>;
  return (
    <InjuryDetailSheet title="Demonstration video" onClose={onClose} busy={pending} panelClassName={media ? layout.dialog : undefined}>
      <div className={`${styles.sheet} ${layout.content}`} data-preview={Boolean(media)}>
        <div className={layout.settings}>
        <p className="muted">Optional · Up to 30 seconds · Private</p>
        {error ? <p role="alert">{error}</p> : null}
        {!choice ? <div className={layout.choices}>
          <button type="button" className="secondary-button" disabled={!settings?.uploads_available} onClick={() => setChoice("upload")}>Upload video</button>
          <button type="button" className="ghost-button" disabled={!settings?.youtube_available} onClick={() => setChoice("youtube")}>YouTube link</button>
          {settings && !settings.uploads_available ? <small className="muted">Uploads are unavailable right now. You can save without a video.</small> : null}
        </div> : choice === "upload" ? <label>
          <span>Video · MP4, MOV or WebM</span>
          <input type="file" accept="video/mp4,video/quicktime,video/webm" disabled={pending} onChange={(e) => void upload(e.target.files?.[0])} />
        </label> : media ? <details><summary>Edit clip</summary>{clipForm}</details> : clipForm}
        {status ? <p role="status">{status}</p> : null}
        {choice ? <details><summary>Video options</summary><button type="button" className="ghost-button" disabled={pending}
          onClick={() => { setChoice(undefined); changed(); }}>Change video source</button></details> : null}
        </div>
        {media ? <div className={layout.preview}><PrivateVideoPlayer key={media.id} media={media} name={name} />
          <button type="button" className="cta" onClick={() => onAttach(media.id)}>Use video</button></div> : null}
      </div>
    </InjuryDetailSheet>
  );
}
