"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { deleteCustomPlan, getCustomPlan, listCustomPlans, saveCustomPlan } from "@/lib/api";
import type { CustomDose, CustomPlan, CustomSession, LibraryEntry } from "@/lib/api-schema.generated";
import { DrillPreview, TrainingLibrary } from "./training-library";
import styles from "./custom-plan-builder.module.css";

type Exercise = Omit<CustomSession["exercises"][number], "snapshot"> & { snapshot: LibraryEntry };
type Session = Omit<CustomSession, "exercises"> & { exercises: Exercise[] };
type Draft = { id?: string; name: string; sessions: Session[] };
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
const emptyDraft = (): Draft => ({ name: "My Training Plan", sessions: [] });
const incomplete = (dose: CustomDose) => dose.mode === "reps" ? !dose.sets || !dose.reps : !dose.duration_seconds;

function DoseEditor({ exercise, onChange }: { exercise: Exercise; onChange: (dose: CustomDose) => void }) {
  const dose = exercise.dose;
  function number(field: "sets" | "reps" | "duration_seconds" | "rest_seconds", label: string, min: number, max: number) {
    return <label><span>{label}</span><input aria-label={`${exercise.snapshot.name} ${label}`} type="number" inputMode="numeric"
      min={min} max={max} step={1} value={dose[field] ?? ""}
      onChange={event => onChange({ ...dose, [field]: event.target.value === "" ? null : Number(event.target.value) })} /></label>;
  }
  return <div className={styles.dose}>
    <label><span>Dose</span><select aria-label={`${exercise.snapshot.name} Dose`} value={dose.mode}
      onChange={event => onChange({ ...dose, mode: event.target.value as CustomDose["mode"], reps: null, duration_seconds: null })}>
      <option value="reps">Sets × reps</option><option value="duration">Duration</option>
    </select></label>
    {number("sets", "Sets", 1, 100)}
    {dose.mode === "reps" ? number("reps", "Reps", 1, 1000) : number("duration_seconds", "Duration (sec)", 1, 36000)}
    {number("rest_seconds", "Rest (sec)", 0, 3600)}
    <details className={styles.optional}><summary>Load / intensity</summary>
      <label><span>Optional load or intensity</span><input aria-label={`${exercise.snapshot.name} Load or intensity`} maxLength={80}
        placeholder={exercise.snapshot.content_type === "strength_power" ? "e.g. 40 kg or RPE 7" : "e.g. easy pace or RPE 7"}
        value={dose.load_or_intensity ?? ""} onChange={event => onChange({ ...dose, load_or_intensity: event.target.value || null })} /></label>
    </details>
  </div>;
}

export function CustomPlanBuilder({ accessToken }: { accessToken: string }) {
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [plans, setPlans] = useState<CustomPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [listRetry, setListRetry] = useState(0);
  const [pending, setPending] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selecting, setSelecting] = useState<string | null>(null);
  const [preview, setPreview] = useState<LibraryEntry | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void listCustomPlans(accessToken, controller.signal).then(value => {
      if (!controller.signal.aborted) setPlans(value);
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load custom plans.");
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [accessToken, listRetry]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function change(next: Draft) { setDraft(next); setDirty(true); setMessage(null); setConfirmDelete(false); }
  function sessionChange(id: string, update: (session: Session) => Session) {
    change({ ...draft, sessions: draft.sessions.map(session => session.id === id ? update(session) : session) });
  }
  function canLeave() { return !dirty || window.confirm("Discard unsaved changes?"); }

  async function save() {
    setPending(true); setError(null); setMessage(null);
    try {
      const saved = await saveCustomPlan(accessToken, { name: draft.name, sessions: draft.sessions.map(session => ({
        id: session.id, name: session.name, weekday: session.weekday,
        exercises: session.exercises.map(exercise => ({ id: exercise.id, catalogue_id: exercise.catalogue_id, dose: exercise.dose })),
      })) }, draft.id);
      setDraft(saved); setDirty(false);
      setPlans(previous => [saved, ...previous.filter(plan => plan.id !== saved.id)]);
      setMessage(saved.incomplete ? "Draft saved. Some sessions or doses are incomplete." : "Plan saved.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save plan."); }
    finally { setPending(false); }
  }

  async function open(id: string) {
    if (!canLeave()) return;
    setPending(true); setError(null); setMessage(null); setConfirmDelete(false);
    try { setDraft(await getCustomPlan(accessToken, id)); setDirty(false); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to open plan."); }
    finally { setPending(false); }
  }

  async function remove() {
    if (!draft.id) return;
    setPending(true); setError(null);
    try {
      await deleteCustomPlan(accessToken, draft.id);
      setPlans(previous => previous.filter(plan => plan.id !== draft.id));
      setDraft(emptyDraft()); setDirty(false); setConfirmDelete(false); setMessage("Plan deleted.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to delete plan."); }
    finally { setPending(false); }
  }

  if (selecting) return <TrainingLibrary accessToken={accessToken} onBack={() => setSelecting(null)} onSelect={entry => {
    if (entry.category !== "training") return;
    sessionChange(selecting, session => ({ ...session, exercises: [...session.exercises, {
      id: crypto.randomUUID(), catalogue_id: entry.catalogue_id, snapshot: entry, incomplete: true,
      dose: { mode: entry.content_type === "strength_power" ? "reps" : "duration", sets: null, reps: null,
        duration_seconds: null, rest_seconds: null, load_or_intensity: null },
    }] }));
    setSelecting(null);
  }} />;

  return <section className={styles.builder} aria-label="Custom training plan builder">
    <header className={styles.header}>
      <Link href="/plans" onClick={event => { if (pending || !canLeave()) event.preventDefault(); }}>← Plans</Link>
      <p className="kicker">UNLXCK / SELF-DIRECTED</p>
      <h1>MY TRAINING PLAN</h1>
      <p className="muted">Custom plans are self-directed and aren&apos;t checked against your training readiness.</p>
    </header>
    {error ? <p className="error-banner" role="alert">{error}</p> : null}
    {message ? <p role="status">{message}</p> : null}
    <form onSubmit={event => { event.preventDefault(); void save(); }}>
      <fieldset disabled={pending} className={styles.editor}>
        <label className={styles.planName}><span>Plan name</span><input required maxLength={100} value={draft.name}
          onChange={event => change({ ...draft, name: event.target.value })} /></label>
        {draft.sessions.map((session, sessionIndex) => <section key={session.id} className={styles.session} aria-label={`Session ${sessionIndex + 1}`}>
          <div className={styles.sessionHead}>
            <label><span>Day</span><select aria-label={`Session ${sessionIndex + 1} Day`} value={session.weekday ?? ""}
              onChange={event => sessionChange(session.id, current => ({ ...current, weekday: event.target.value as Session["weekday"] || null }))}>
              <option value="">Unassigned</option>{weekdays.map(day => <option key={day}>{day}</option>)}
            </select></label>
            <label><span>Session name</span><input required maxLength={100} value={session.name} aria-label={`Session ${sessionIndex + 1} name`}
              onChange={event => sessionChange(session.id, current => ({ ...current, name: event.target.value }))} /></label>
            <button type="button" className="ghost-button" aria-label={`Remove session ${sessionIndex + 1}`}
              onClick={() => change({ ...draft, sessions: draft.sessions.filter(current => current.id !== session.id) })}>Remove</button>
          </div>
          <ol className={styles.exercises}>
            {session.exercises.map((exercise, index) => <li key={exercise.id} className={styles.exercise}>
              <div className={styles.exerciseHead}>
                <button type="button" className={styles.exerciseName} onClick={() => setPreview(exercise.snapshot)}>{exercise.snapshot.name}</button>
                {incomplete(exercise.dose) ? <span className={styles.incomplete}>Incomplete dose</span> : null}
                <div className={styles.order}>
                  {([-1, 1] as const).map(direction => <button type="button" key={direction} className="ghost-button"
                    disabled={index + direction < 0 || index + direction >= session.exercises.length}
                    aria-label={`Move ${exercise.snapshot.name} ${direction === -1 ? "up" : "down"}`}
                    onClick={() => sessionChange(session.id, current => {
                      const exercises = [...current.exercises];
                      [exercises[index], exercises[index + direction]] = [exercises[index + direction], exercises[index]];
                      return { ...current, exercises };
                    })}>{direction === -1 ? "↑" : "↓"}</button>)}
                  <button type="button" className="ghost-button" aria-label={`Remove ${exercise.snapshot.name}`}
                    onClick={() => sessionChange(session.id, current => ({ ...current, exercises: current.exercises.filter(item => item.id !== exercise.id) }))}>×</button>
                </div>
              </div>
              <DoseEditor exercise={exercise} onChange={dose => sessionChange(session.id, current => ({ ...current,
                exercises: current.exercises.map(item => item.id === exercise.id ? { ...item, dose } : item),
              }))} />
            </li>)}
          </ol>
          {!session.exercises.length ? <p className="muted">Add exercises to this session. Empty sessions save as drafts.</p> : null}
          <button type="button" className="secondary-button" disabled={session.exercises.length >= 100} onClick={() => setSelecting(session.id)}>+ Add Exercise</button>
        </section>)}
        <div className={styles.actions}>
          <button type="button" className="secondary-button" disabled={draft.sessions.length >= 28} onClick={() => change({ ...draft,
            sessions: [...draft.sessions, { id: crypto.randomUUID(), name: "Training", weekday: null, exercises: [] }],
          })}>+ Add Session</button>
          <button type="submit" className="cta">{pending ? "Saving…" : "Save Plan"}</button>
          <span className="muted">{dirty ? "Unsaved changes" : draft.id ? "Saved custom plan" : "New custom plan"}</span>
        </div>
      </fieldset>
    </form>
    <section className={styles.saved} aria-label="Saved custom plans">
      <div className={styles.actions}><h2>Custom plans</h2><button className="ghost-button" disabled={pending} onClick={() => {
        if (canLeave()) { setDraft(emptyDraft()); setDirty(false); setConfirmDelete(false); setError(null); setMessage(null); }
      }}>New plan</button></div>
      {loading ? <p role="status">Loading custom plans…</p> : plans.length ? <ul>{plans.map(plan => <li key={plan.id}>
        <button disabled={pending} onClick={() => void open(plan.id)}>{plan.name}</button>
        <span className="muted">Self-directed{plan.incomplete ? " · Draft" : ""}</span>
      </li>)}</ul> : <p className="muted">No saved custom plans yet.</p>}
      {error && !loading ? <button className="ghost-button" disabled={pending} onClick={() => { setError(null); setLoading(true); setListRetry(value => value + 1); }}>Refresh saved plans</button> : null}
      {draft.id ? <div className={styles.actions}>{confirmDelete ? <>
        <span>Delete this custom plan?</span><button className="secondary-button" disabled={pending} onClick={() => void remove()}>Confirm delete</button>
        <button className="ghost-button" disabled={pending} onClick={() => setConfirmDelete(false)}>Keep plan</button>
      </> : <button className="ghost-button" disabled={pending} onClick={() => setConfirmDelete(true)}>Delete plan</button>}</div> : null}
    </section>
    {preview ? <DrillPreview entry={preview} token={accessToken} onClose={() => setPreview(null)} selfDirected /> : null}
  </section>;
}
