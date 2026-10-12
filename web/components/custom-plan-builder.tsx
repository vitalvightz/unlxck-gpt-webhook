"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { deleteCustomPlan, getCommunityExercise, getCustomDoseSuggestion, getCustomPlan, publishCustomPlan, saveCustomPlan } from "@/lib/api";
import type { MeResponse } from "@/lib/types";
import { customSchedulePrefill, customScheduleIssues, prepareCustomSession, sessionNames, customPlanError } from "@/lib/custom-plan-schedule";
import type {
  CommunityEntry,
  CustomDoseSuggestion,
  CustomExercise,
  CustomSession,
  LibraryEntry,
  ManualExercise,
} from "@/lib/api-schema.generated";
import { InjuryDetailSheet } from "./today/injury-detail-sheet";
import { DrillPreview, TrainingLibrary } from "./training-library";
import { CustomDoseEditor } from "./custom-dose-editor";
import { CommunityContributionSheet, CommunityExercisePreview, communityDetailsChanged } from "./community-exercises";
import { PrivateExerciseVideo, PrivateExerciseVideoSheet } from "./private-exercise-video";
import { blankDose, doseSummary, doseIncomplete } from "@/lib/custom-plan-dose";
import styles from "./custom-plan-builder.module.css";
type Exercise = (Omit<CustomExercise, "snapshot"> & { snapshot: LibraryEntry }) | ManualExercise;
type Session = Omit<CustomSession, "exercises" | "session_type"> & { exercises: Exercise[]; session_type?: CustomSession["session_type"] };
type Draft = { id?: string; name: string; sessions: Session[]; incomplete?: boolean };
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
function orderedDraft(draft: Draft): Draft {
  const day = (session: Session) => session.weekday ? weekdays.indexOf(session.weekday) : 7;
  return { ...draft, sessions: [...draft.sessions].sort((a, b) => day(a) - day(b)) };
}
const nameOf = (e: Exercise) => (e.origin === "manual" ? e.name : e.snapshot.name);
function PencilIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}
export function CustomPlanBuilder({ accessToken, planId, onboarding = null }: { accessToken: string; planId?: string; onboarding?: MeResponse | null }) {
  const router = useRouter();
  const [draft, setDraft] = useState<Draft>(() => ({
    name: "My Training Plan",
    sessions: planId ? [] : customSchedulePrefill(onboarding),
  }));
  const [loading, setLoading] = useState(!!planId),
    [retry, setRetry] = useState(0),
    [pending, setPending] = useState(false),
    [dirty, setDirty] = useState(false);
  const [opened, setOpened] = useState(!planId);
  const [error, setError] = useState<string>(),
    [message, setMessage] = useState<string>();
  const [selecting, setSelecting] = useState<string>(),
    [editing, setEditing] = useState<{
      sessionId: string;
      exercise: Exercise;
      fresh?: boolean;
      position: number;
      original: Exercise;
      originalPosition: number;
    }>();
  const [sessionEdit, setSessionEdit] = useState<Session>(),
    [preview, setPreview] = useState<LibraryEntry>();
  const [videoOpen, setVideoOpen] = useState(false), [communityOpen, setCommunityOpen] = useState(false), [communityPreview, setCommunityPreview] = useState<string>();
  const [linkedCommunity, setLinkedCommunity] = useState<{ id: string; entry?: CommunityEntry; error?: boolean }>();
  const editingCommunityId = editing?.exercise.origin === "manual" ? editing.exercise.community_id : null;
  useEffect(() => {
    if (!editingCommunityId) return;
    const request = new AbortController();
    void getCommunityExercise(accessToken, editingCommunityId, 'owned', request.signal).then(entry => {
      if (!request.signal.aborted) setLinkedCommunity({ id: editingCommunityId, entry });
    }).catch(() => {
      if (!request.signal.aborted) setLinkedCommunity({ id: editingCommunityId, error: true });
    });
    return () => request.abort();
  }, [accessToken, editingCommunityId, communityOpen]);
  const [suggestion, setSuggestion] = useState<CustomDoseSuggestion>(),
    [suggestionError, setSuggestionError] = useState<string>(),
    [suggesting, setSuggesting] = useState(false);
  const suggestionRequest = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const sheetDirty =
    Boolean(
      editing &&
      (JSON.stringify(editing.exercise) !== JSON.stringify(editing.original) ||
        editing.position !== editing.originalPosition),
    ) ||
    Boolean(
      sessionEdit &&
      JSON.stringify(sessionEdit) !== JSON.stringify(draft.sessions.find((s) => s.id === sessionEdit.id)),
    );
  const unsaved = dirty || sheetDirty;
  const releaseGuard = useRef<() => Promise<void>>(async () => {});
  const loaded = useRef(false),
    heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!planId || loaded.current) return;
    let active = true;
    void getCustomPlan(accessToken, planId)
      .then((plan) => {
        if (active) {
          loaded.current = true;
          setOpened(true);
          setError(undefined);
          const repaired = orderedDraft({ ...plan, sessions: plan.sessions.map(s => prepareCustomSession(s, onboarding)) });
          setDraft(repaired);
          setDirty(JSON.stringify(repaired.sessions) !== JSON.stringify(plan.sessions));
          window.scrollTo(0, 0);
        }
      })
      .catch((reason) => {
        if (active) setError(customPlanError(reason, "Unable to open plan."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [accessToken, planId, retry, onboarding]);
  useEffect(() => {
    if (!loading && loaded.current) heading.current?.focus({ preventScroll: true });
  }, [loading]);
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    // Keep a same-URL entry while dirty so Back can confirm without losing edits.
    const state = { ...window.history.state, customDraftGuard: true };
    window.history.pushState(state, "", window.location.href);
    const back = () => {
      if (!window.confirm("Discard unsaved changes?")) {
        window.history.pushState(state, "", window.location.href);
        return;
      }
      window.removeEventListener("popstate", back);
      setDirty(false);
      window.history.back();
    };
    const release = () => {
      window.removeEventListener("popstate", back);
      if (!window.history.state?.customDraftGuard) return Promise.resolve();
      return new Promise<void>((resolve) => {
        window.addEventListener("popstate", () => resolve(), { once: true });
        window.history.back();
      });
    };
    releaseGuard.current = release;
    window.addEventListener("popstate", back);
    const click = (e: MouseEvent) => {
      const anchor = (e.target as Element)?.closest<HTMLAnchorElement>("a[href]");
      if (!anchor || e.ctrlKey || e.metaKey || anchor.target === "_blank") return;
      e.preventDefault();
      e.stopPropagation();
      if (window.confirm("Discard unsaved changes?"))
        void release().then(() => {
          setDirty(false);
          router.push(anchor.href);
        });
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", click, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", click, true);
      window.removeEventListener("popstate", back);
      releaseGuard.current = async () => {};
    };
  }, [unsaved, router]);
  function change(next: Draft) {
    setDraft(orderedDraft(next));
    setDirty(true);
    setMessage(undefined);
  }
  function sessionChange(id: string, update: (s: Session) => Session) {
    change({
      ...draft,
      sessions: draft.sessions.map((s) => (s.id === id ? update(s) : s)),
    });
  }
  function edit(sessionId: string, exercise: Exercise, fresh = false) {
    suggestionRequest.current++;
    setSuggesting(false);
    setSuggestion(undefined);
    setSuggestionError(undefined);
    setEditing({
      sessionId,
      exercise,
      fresh,
      position: draft.sessions.find((s) => s.id === sessionId)?.exercises.findIndex((e) => e.id === exercise.id) ?? 0,
      original: exercise,
      originalPosition:
        draft.sessions.find((s) => s.id === sessionId)?.exercises.findIndex((e) => e.id === exercise.id) ?? 0,
    });
  }
  async function suggest() {
    if (!editing || editing.exercise.origin !== "catalogue") return;
    const request = ++suggestionRequest.current;
    setSuggesting(true);
    setSuggestionError(undefined);
    try {
      const result = await getCustomDoseSuggestion(accessToken, editing.exercise.catalogue_id);
      if (request === suggestionRequest.current) setSuggestion(result);
    } catch (e) {
      if (request === suggestionRequest.current)
        setSuggestionError(customPlanError(e, "Unable to load source suggestion."));
    } finally {
      if (request === suggestionRequest.current) setSuggesting(false);
    }
  }
  const issues = customScheduleIssues(draft.sessions);
  const draftValid = Boolean(draft.name.trim()) && draft.sessions.every(s => s.name.trim() && s.exercises.every(e => nameOf(e).trim()));
  const publishable = draftValid && issues.length === 0;
  const emptyWorkouts = new Set(issues.filter(issue => issue.message.includes("no exercises")).map(issue => issue.sessionId)).size;
  const saveBar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const bar = saveBar.current;
    if (!bar || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      bar.closest<HTMLElement>(`.${styles.builder}`)?.style.setProperty("--custom-save-height", `${bar.offsetHeight}px`);
    });
    observer.observe(bar);
    return () => observer.disconnect();
  }, [loading, selecting]);
  async function save(viewPlan = false) {
    if (!draftValid || (viewPlan && !publishable)) return;
    setPending(true);
    setError(undefined);
    try {
      const saved = await saveCustomPlan(
        accessToken,
        {
          name: draft.name,
          sessions: draft.sessions.map((s) => ({
            id: s.id,
            name: s.name,
            weekday: s.weekday,
            session_type: s.session_type ?? "mixed",
            exercises: s.exercises.map((e) =>
              e.origin === "manual"
                ? {
                    id: e.id,
                    origin: e.origin,
                    name: e.name,
                    equipment: e.equipment,
                    notes: e.notes,
                    media_id: e.media_id,
                    community_id: e.community_id,
                    community_revision_id: e.community_revision_id,
                    dose: e.dose,
                  }
                : {
                    id: e.id,
                    origin: "catalogue" as const,
                    catalogue_id: e.catalogue_id,
                    dose: e.dose,
                  },
            ),
          })),
        },
        draft.id,
      );
      if (!mounted.current) return;
      await releaseGuard.current();
      setDraft(orderedDraft(saved));
      setOpened(true);
      setDirty(false);
      setMessage(saved.incomplete ? "Draft saved. Finish the workouts listed below when ready." : "Plan saved. View your plan to activate it.");
      window.history.replaceState(window.history.state, "", `/plans/custom?plan=${saved.id}`);
      loaded.current = true;
      if (viewPlan) {
        const published = await publishCustomPlan(accessToken, saved.id);
        router.push(`/plans/${published.plan_id}`);
      }
    } catch (e) {
      setError(customPlanError(e, "Unable to save plan."));
    } finally {
      setPending(false);
    }
  }
  if (loading)
    return (
      <section className={styles.builder}>
        <p role="status">Opening custom plan…</p>
      </section>
    );
  if (planId && !opened)
    return (
      <section className={styles.builder}>
        <Link href="/plans#custom-plans">← Saved plans</Link>
        <p role="alert">{error}</p>
        <button
          className="ghost-button"
          onClick={() => {
            setLoading(true);
            setError(undefined);
            setRetry((n) => n + 1);
          }}
        >
          Retry opening plan
        </button>
      </section>
    );
  if (selecting)
    return (
      <TrainingLibrary
        accessToken={accessToken}
        onBack={() => setSelecting(undefined)}
        onSelectCommunity={(entry) => {
          sessionChange(selecting, s => ({ ...s, exercises: [...s.exercises, { id: crypto.randomUUID(), origin: 'manual', name: entry.name,
            equipment: entry.equipment, notes: entry.notes, media_id: null, community_id: null, community_revision_id: entry.revision_id,
            incomplete: true, dose: blankDose() }] }));
          setSelecting(undefined);
        }}
        onSelect={(entry) => {
          if (entry.category !== "training") return;
          sessionChange(selecting, (s) => ({
            ...s,
            exercises: [
              ...s.exercises,
              {
                id: crypto.randomUUID(),
                origin: "catalogue",
                catalogue_id: entry.catalogue_id,
                snapshot: entry,
                incomplete: true,
                dose: blankDose(),
              },
            ],
          }));
          setSelecting(undefined);
        }}
      />
    );
  return (
    <section className={styles.builder} aria-label="Custom training plan builder">
      <header className={styles.header}>
        <Link href="/plans#custom-plans">← Saved plans</Link>
        <div className={styles.row}>
          <h1 ref={heading} tabIndex={-1}>
            {draft.name}
          </h1>
          <span className={styles.badge}>{dirty ? "Unsaved" : draft.id ? "Saved" : "New"}</span>
        </div>
        <p className="muted">Choose what happens each day. Unselected days are rest days.</p>
      </header>
      {error ? (
        <p className="error-banner" role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status">
          {message} <Link href="/plans#custom-plans">View saved plans</Link>
        </p>
      ) : null}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <fieldset className={styles.editor} disabled={pending}>
          <label>
            <span>Plan name</span>
            <input
              required
              maxLength={100}
              value={draft.name}
              onChange={(e) => change({ ...draft, name: e.target.value })}
            />
          </label>
          <div className={styles.calendar} aria-label="Weekly training calendar">
            {weekdays.map(day => {
              const sessions = draft.sessions.filter(s => s.weekday === day);
              return <button key={day} type="button" className="ghost-button" aria-label={`Schedule ${day}`}
                disabled={!sessions.length && draft.sessions.length >= 28}
                onClick={() => {
                  if (sessions.length) { setSessionEdit(sessions[0]); return; }
                  const session: Session = { id: crypto.randomUUID(), name: "Training", weekday: day, session_type: "mixed", exercises: [] };
                  change({ ...draft, sessions: [...draft.sessions, session] });
                  setSessionEdit(session);
                }}>
                <strong>{day.slice(0, 3)}</strong>
                <small>{sessions.length ? sessions.map(s => sessionNames[s.session_type ?? "mixed"]).join(" / ") : "Rest day — Nothing scheduled"}</small>
              </button>;
            })}
          </div>
          {draft.sessions.map((s, i) => (
            <section key={s.id} className={styles.session} aria-label={`Session ${i + 1}`}>
              <div className={styles.row}>
                <div>
                  <small className={styles.weekday}>{s.weekday ?? "Unassigned"}</small>
                  <h2>{s.name}</h2>
                </div>
                <button
                  type="button"
                  className={styles.editButton}
                  aria-label={`Edit session ${i + 1}`}
                  title="Edit session"
                  onClick={() => setSessionEdit(s)}
                >
                  <PencilIcon />
                </button>
              </div>
              {s.session_type !== "rest" ? <ol className={styles.exercises}>
                {s.exercises.map((e) => (
                  <li key={e.id} className={styles.exercise}>
                    <div className={styles.row}>
                      <div className={styles.exerciseText}>
                        <strong>{nameOf(e)}</strong>
                        <small>
                          {e.origin === "manual" ? "My exercise · " : ""}
                          {doseSummary(e.dose)}
                        </small>
                        {e.origin === "manual" && e.notes?.startsWith("Editable suggestion only:") ? <small>{e.notes}</small> : null}
                      </div>
                      <button
                        type="button"
                        className={styles.editButton}
                        aria-label={`Edit dose for ${nameOf(e)}`}
                        title="Edit dose"
                        onClick={() => edit(s.id, e)}
                      >
                        <PencilIcon />
                      </button>
                    </div>
                  </li>
                ))}
              </ol> : <p className="muted">Rest day — Nothing scheduled. {s.exercises.length ? "Saved exercises are kept if you switch back to training." : ""}</p>}
              {!s.exercises.length && s.session_type !== "rest" ? <p className="muted">{s.session_type === "recovery" ? "Recovery day — No exercises required." : ["sparring", "skill"].includes(s.session_type ?? "mixed") ? "Coach-led day — Add editable rounds if useful." : "Workout needs exercises."}</p> : null}
              {s.session_type === "recovery" && s.exercises.length ? <p className="muted">Optional recovery work — No workout completion required.</p> : null}
              {s.session_type !== "rest" ? <div className={styles.row}>
                <button
                  type="button"
                  className="ghost-button"
                  disabled={s.exercises.length >= 100}
                  onClick={() => setSelecting(s.id)}
                >
                  Add from library
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  disabled={s.exercises.length >= 100}
                  onClick={() =>
                    edit(
                      s.id,
                      {
                        id: crypto.randomUUID(),
                        origin: "manual",
                        name: "",
                        equipment: null,
                        notes: null,
                        media_id: null,
                        community_id: null,
                        community_revision_id: null,
                        dose: blankDose(),
                        incomplete: true,
                      },
                      true,
                    )
                  }
                >
                  Create my exercise
                </button>
              </div> : null}
            </section>
          ))}
          <button
            type="button"
            className="secondary-button"
            disabled={draft.sessions.length >= 28}
            onClick={() =>
              change({
                ...draft,
                sessions: [
                  ...draft.sessions,
                  {
                    id: crypto.randomUUID(),
                    name: "Training",
                    weekday: null,
                    exercises: [],
                  },
                ],
              })
            }
          >
            + Add Session
          </button>
          <div className={styles.saveBar} ref={saveBar}>
            <span role="status">
              {publishable ? "Ready to activate — Your weekly training plan is complete."
                : emptyWorkouts ? `${emptyWorkouts} ${emptyWorkouts === 1 ? "workout needs" : "workouts need"} exercises`
                  : "Your weekly plan needs attention"}
              {dirty ? " · Unsaved changes" : ""}
            </span>
            {issues.length ? <ul className={styles.issues}>{issues.map((issue, index) => <li key={index}>
              {issue.message} {issue.sessionId ? <button type="button" className="ghost-button" onClick={() => {
                const session = draft.sessions.find(s => s.id === issue.sessionId)!;
                const exercise = session.exercises.find(e => doseIncomplete(e.dose));
                if (exercise) edit(session.id, exercise); else setSessionEdit(session);
              }}>Edit {draft.sessions.find(s => s.id === issue.sessionId)?.weekday ?? "session"}</button> : null}
            </li>)}</ul> : <span>View your plan, then activate it from Plan Detail.</span>}
            <button type="submit" className="cta" disabled={!draftValid}>
              {pending ? "Saving…" : "Save draft"}
            </button>
            <button type="button" className="cta" disabled={!publishable} onClick={() => void save(true)}>
              Save &amp; view plan
            </button>
          </div>
        </fieldset>
      </form>
      {draft.id ? (
        <button
          className="ghost-button"
          disabled={pending}
          onClick={async () => {
            if (!window.confirm("Delete this custom plan?")) return;
            setPending(true);
            try {
              await deleteCustomPlan(accessToken, draft.id!);
              setDirty(false);
              router.push("/plans#custom-plans");
            } catch (e) {
              setError(customPlanError(e, "Unable to delete plan."));
              setPending(false);
            }
          }}
        >
          Delete plan
        </button>
      ) : null}
      {sessionEdit ? (
        <InjuryDetailSheet
          title="Edit session"
          onClose={() => {
            const original = draft.sessions.find((s) => s.id === sessionEdit.id);
            if (JSON.stringify(original) === JSON.stringify(sessionEdit) || window.confirm("Discard session edits?")) {
              if (sheetDirty && !dirty) void releaseGuard.current().then(() => setSessionEdit(undefined));
              else setSessionEdit(undefined);
            }
          }}
        >
          <form
            className={styles.sheet}
            onSubmit={(e) => {
              e.preventDefault();
              sessionChange(sessionEdit.id, () => sessionEdit);
              setSessionEdit(undefined);
            }}
          >
            <label>
              <span>Session name</span>
              <input
                required
                maxLength={100}
                value={sessionEdit.name}
                onChange={(e) => setSessionEdit({ ...sessionEdit, name: e.target.value })}
              />
            </label>
            <label>
              <span>Day</span>
              <select
                aria-label="Day"
                value={sessionEdit.weekday ?? ""}
                onChange={(e) =>
                  setSessionEdit({
                    ...sessionEdit,
                    weekday: (e.target.value as Session["weekday"]) || null,
                  })
                }
              >
                <option value="">Unassigned</option>
                {weekdays.map((day) => (
                  <option key={day}>{day}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Session type</span>
              <select aria-label="Session type" value={sessionEdit.session_type ?? "mixed"}
                onChange={(e) => setSessionEdit(prepareCustomSession({ ...sessionEdit, session_type: e.target.value as CustomSession["session_type"] }, onboarding, sessionEdit.session_type ?? "mixed"))}>
                <option value="mixed">Workout</option>
                <option value="strength_power">Strength / power</option>
                <option value="conditioning">Conditioning</option>
                <option value="skill">Light technical / skill</option>
                <option value="sparring">Hard sparring</option>
                <option value="recovery">Recovery</option>
                <option value="rest">Off / Rest</option>
              </select>
            </label>
            <button className="cta">Done</button>
            <button
              type="button"
              className="ghost-button"
              onClick={() => {
                if (window.confirm("Remove this session and its exercises?")) {
                  change({
                    ...draft,
                    sessions: draft.sessions.filter((s) => s.id !== sessionEdit.id),
                  });
                  setSessionEdit(undefined);
                }
              }}
            >
              Remove session
            </button>
          </form>
        </InjuryDetailSheet>
      ) : null}
      {editing ? (
        <InjuryDetailSheet
          title={editing.fresh ? "Create my exercise" : nameOf(editing.exercise)}
          onClose={() => {
            if (
              (JSON.stringify(editing.original) === JSON.stringify(editing.exercise) &&
                editing.originalPosition === editing.position) ||
              window.confirm("Discard exercise edits?")
            ) {
              suggestionRequest.current++;
              if (sheetDirty && !dirty) void releaseGuard.current().then(() => setEditing(undefined));
              else setEditing(undefined);
            }
          }}
        >
          <form
            className={styles.sheet}
            onSubmit={(event) => {
              event.preventDefault();
              const { sessionId, exercise, fresh, position } = editing;
              sessionChange(sessionId, (s) => {
                if (fresh) return { ...s, exercises: [...s.exercises, exercise] };
                const exercises = s.exercises.filter((e) => e.id !== exercise.id);
                exercises.splice(position, 0, exercise);
                return { ...s, exercises };
              });
              setEditing(undefined);
            }}
          >
            {editing.exercise.origin === "manual" ? (
              <>
                {(["name", "equipment", "notes"] as const).map((field) => (
                  <label key={field}>
                    <span>{field === "name" ? "Exercise name" : `${field} (optional)`}</span>
                    <input
                      required={field === "name"}
                      maxLength={field === "name" ? 100 : field === "notes" ? 2000 : 120}
                      value={(editing.exercise as ManualExercise)[field] ?? ""}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          exercise: {
                            ...editing.exercise,
                            [field]: e.target.value,
                          },
                        })
                      }
                    />
                  </label>
                ))}
                {editing.exercise.community_revision_id ? <button type="button" className="ghost-button" onClick={() => setCommunityPreview(editing.exercise.origin === 'manual' ? editing.exercise.community_revision_id ?? undefined : undefined)}>View community exercise</button> :
                  <button type="button" className="ghost-button" disabled={!editing.exercise.name.trim()} onClick={() => setCommunityOpen(true)}>{editing.exercise.community_id ? 'Community submission' : 'Community · Private'}</button>}
                {editing.exercise.community_id && linkedCommunity?.id === editing.exercise.community_id && linkedCommunity.entry &&
                  communityDetailsChanged(linkedCommunity.entry, editing.exercise) ? <div role="status" className={styles.communityNotice}>
                    {linkedCommunity.entry.media_id !== editing.exercise.media_id
                      ? 'Video not included in community submission yet.' : 'Your community submission has older exercise details.'}
                    <button type="button" className="secondary-button" onClick={() => setCommunityOpen(true)}>Update community submission</button>
                  </div> : null}
                {editing.exercise.community_id && linkedCommunity?.id === editing.exercise.community_id && linkedCommunity.error
                  ? <button type="button" className="ghost-button" onClick={() => setCommunityOpen(true)}>Check community submission</button> : null}
                {editing.exercise.media_id ? <PrivateExerciseVideo token={accessToken} id={editing.exercise.media_id} name={editing.exercise.name} /> : null}
                <button type="button" className="ghost-button" onClick={() => setVideoOpen(true)}>
                  {editing.exercise.media_id ? "Replace video" : "Add video (optional)"}
                </button>
                {editing.exercise.media_id ? <button type="button" className="ghost-button" onClick={() => setEditing((current) =>
                  current?.exercise.origin === "manual" ? { ...current, exercise: { ...current.exercise, media_id: null } } : current,
                )}>Remove video</button> : null}
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() =>
                    setPreview(editing.exercise.origin === "catalogue" ? editing.exercise.snapshot : undefined)
                  }
                >
                  View library exercise
                </button>
                <button type="button" className="ghost-button" disabled={suggesting} onClick={() => void suggest()}>
                  {suggesting ? "Loading source…" : "Suggested format"}
                </button>
                {suggestionError ? <p role="alert">{suggestionError}</p> : null}
                {suggestion ? (
                  <div>
                    <p>{suggestion.original || "No explicit dosage in this source."}</p>
                    {suggestion.dose ? (
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => {
                          if (
                            Object.entries(editing.exercise.dose).some(([k, v]) => k !== "mode" && v != null) &&
                            !window.confirm("Replace the current dose with the source suggestion?")
                          )
                            return;
                          setEditing({
                            ...editing,
                            exercise: {
                              ...editing.exercise,
                              dose: suggestion.dose!,
                            },
                          });
                        }}
                      >
                        Use source suggestion
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </>
            )}
            {!editing.fresh && draft.sessions.find((s) => s.id === editing.sessionId)!.exercises.length > 1 ? (
              <label>
                <span>Position in session</span>
                <select
                  aria-label="Position in session"
                  value={editing.position}
                  onChange={(e) => setEditing({ ...editing, position: Number(e.target.value) })}
                >
                  {draft.sessions
                    .find((s) => s.id === editing.sessionId)!
                    .exercises.map((e, index) => (
                      <option key={e.id} value={index}>
                        {index + 1}
                      </option>
                    ))}
                </select>
              </label>
            ) : null}
            <CustomDoseEditor
              dose={editing.exercise.dose}
              onChange={(dose) =>
                setEditing({
                  ...editing,
                  exercise: { ...editing.exercise, dose },
                })
              }
            />
            <button className="cta">{editing.fresh ? "Add exercise" : "Done"}</button>
            {!editing.fresh ? (
              <>
                <button
                  type="button"
                  className="ghost-button"
                  disabled={draft.sessions.find((s) => s.id === editing.sessionId)!.exercises.length >= 100}
                  onClick={() => {
                    sessionChange(editing.sessionId, (s) => ({
                      ...s,
                      exercises: [...s.exercises, { ...editing.exercise, id: crypto.randomUUID() }],
                    }));
                    setEditing(undefined);
                  }}
                >
                  Copy exercise
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => {
                    if (window.confirm("Remove this exercise?")) {
                      sessionChange(editing.sessionId, (s) => ({
                        ...s,
                        exercises: s.exercises.filter((e) => e.id !== editing.exercise.id),
                      }));
                      setEditing(undefined);
                    }
                  }}
                >
                  Remove exercise
                </button>
              </>
            ) : null}
          </form>
        </InjuryDetailSheet>
      ) : null}
      {preview ? (
        <DrillPreview entry={preview} token={accessToken} onClose={() => setPreview(undefined)} selfDirected />
      ) : null}
      {communityOpen && editing?.exercise.origin === 'manual' ? <CommunityContributionSheet key={accessToken} token={accessToken} exercise={editing.exercise} onClose={() => setCommunityOpen(false)}
        onIdentity={id => setEditing(current => current?.exercise.origin === 'manual' ? { ...current, exercise: { ...current.exercise, community_id: id } } : current)} /> : null}
      {communityPreview ? <CommunityExercisePreview key={`${accessToken}:${communityPreview}`} token={accessToken} revision={communityPreview} onClose={() => setCommunityPreview(undefined)} /> : null}
      {videoOpen && editing?.exercise.origin === "manual" ? <PrivateExerciseVideoSheet
        token={accessToken} name={editing.exercise.name || "My exercise"} onClose={() => setVideoOpen(false)}
        onAttach={(media_id) => {
          setEditing((current) => current?.exercise.origin === "manual" ? {
            ...current, exercise: { ...current.exercise, media_id, community_revision_id: null },
          } : current);
          setVideoOpen(false);
          if (editingCommunityId) setCommunityOpen(true);
        }} /> : null}
    </section>
  );
}
