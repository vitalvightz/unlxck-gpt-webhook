"use client";

import { type FormEvent, useId, useRef, useState } from "react";

import {
  BodyMap,
  type BodyMapSelection,
  type BodyMapSeverity,
  type BodyMapSide,
} from "@/components/body-map";
import { CustomSelect } from "@/components/custom-select";
import { SegmentGroup } from "@/components/today/segment-group";
import { useToast } from "@/components/toast-provider";
import { submitTodayInjuryCheckin } from "@/lib/api";
import { normalizeInjuryLabel, resolveInjuryTypeLabel } from "@/lib/injury-display";
import { TODAY_INJURY_MAX_WORDS } from "@/lib/input-limits";
import {
  NO_TODAY_INJURY_TYPE,
  TODAY_INJURY_TYPE_OPTIONS,
  type TodayInjuryTypeSelection,
  composeTodayInjuryDescription,
  isInjuryEntryLimited,
  limitInjuryEntryText,
} from "@/lib/today-injury-input";
import type {
  Coverable,
  Drainage,
  FrictionOrContactProblem,
  InjuryFlagRecord,
  InjuryFlagSeverity,
  SkinIntegrity,
  TodayInjuryCheckinStatus,
  TodayInjuryDeclaration,
} from "@/lib/types";

// "Same" is deliberately NOT an option. An injury left untouched stays exactly
// where it is (the backend keeps it "ongoing"), so a per-day "nothing changed"
// tap was pure ceremony — and a bright, pre-selectable "Same" button read to
// athletes as a required daily confirmation. The check-in now only asks for a
// CHANGE: easing, worse, or cleared. Silence means "same".
const INJURY_STATUS_ACTIONS: Array<{ value: TodayInjuryCheckinStatus; label: string }> = [
  { value: "improving", label: "Easing" },
  { value: "worse", label: "Worse" },
  { value: "resolved", label: "Cleared" },
];

// Surface (skin) follow-up ----------------------------------------------------
// A worsening blister, graze or cut is routed by what the skin is doing, not by
// a blanket "injury is worse" rule — so a worse report on a KNOWN skin injury
// asks these five questions first. They are never shown for other injuries.
//
// The same answers are what a wound is still restricted BY, so they also need a
// way back down: an injury currently held at "no contact" or "needs checking"
// gets a shortened recheck on Easing / Same, which is how an open blister that
// has closed over stops blocking contact. Nothing is ever cleared without the
// athlete confirming it — the recheck opens pre-filled with what is on record.

/** Backend classes that mean "this is a skin injury we route by skin answers". */
const SURFACE_FOLLOW_UP_CLASSES = new Set([
  "stable_surface",
  "surface_local_restriction",
  "surface_no_contact",
]);

/** Classes where the stored skin state is actively restricting training, so an
 * improving report has to say what changed before the restriction can lift. */
const SURFACE_RECHECK_CLASSES = new Set(["surface_no_contact", "surface_medical_review"]);

function needsSurfaceFollowUp(injury: InjuryFlagRecord): boolean {
  return SURFACE_FOLLOW_UP_CLASSES.has(injury.surface_class ?? "non_surface");
}

function needsSurfaceRecheck(injury: InjuryFlagRecord): boolean {
  return SURFACE_RECHECK_CLASSES.has(injury.surface_class ?? "non_surface");
}

/** Bleeding and leaking read as one question to the athlete; the answer maps to
 * the two structured fields the backend routes on. */
type BleedAnswer = "no" | "controlled" | "leaking" | "uncontrolled";

const BLEED_ANSWER_FIELDS: Record<
  BleedAnswer,
  Pick<TodayInjuryDeclaration, "bleeding_status" | "drainage">
> = {
  no: { bleeding_status: "none", drainage: "none" },
  controlled: { bleeding_status: "controlled", drainage: "none" },
  leaking: { bleeding_status: "controlled", drainage: "present" },
  uncontrolled: { bleeding_status: "uncontrolled", drainage: "unknown" },
};

const SKIN_INTEGRITY_OPTIONS: Array<{ value: SkinIntegrity; label: string }> = [
  { value: "intact", label: "Still closed" },
  { value: "open", label: "Open or burst" },
  { value: "unknown", label: "Not sure" },
];

const BLEED_OPTIONS: Array<{ value: BleedAnswer; label: string }> = [
  { value: "no", label: "No" },
  { value: "controlled", label: "A little, stops" },
  { value: "leaking", label: "Weeping" },
  { value: "uncontrolled", label: "Won't stop" },
];

const INFECTION_SIGN_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "spreading_redness", label: "Spreading redness" },
  { value: "pus", label: "Pus" },
  { value: "heat_or_swelling", label: "Hot or swollen" },
  { value: "fever", label: "Fever" },
];

const COVERABLE_OPTIONS: Array<{ value: Coverable; label: string }> = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "unknown", label: "Not sure" },
];

const FRICTION_OPTIONS: Array<{ value: FrictionOrContactProblem; label: string }> = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "unknown", label: "Not sure" },
];

type SurfaceFollowUpAnswers = {
  skin_integrity: SkinIntegrity;
  bleed: BleedAnswer;
  // Bleeding and drainage are one question to the athlete but two stored facts,
  // and "Won't stop" does not say anything about drainage. These two remember
  // what was on record so an untouched recheck can send the stored drainage back
  // instead of overwriting a recorded "present" with "unknown".
  initialBleed: BleedAnswer;
  storedDrainage: Drainage | null;
  infection_signs: string[];
  coverable: Coverable;
  friction_or_contact_problem: FrictionOrContactProblem;
};

const EMPTY_SURFACE_ANSWERS: SurfaceFollowUpAnswers = {
  skin_integrity: "unknown",
  bleed: "no",
  initialBleed: "no",
  storedDrainage: null,
  infection_signs: [],
  coverable: "unknown",
  friction_or_contact_problem: "unknown",
};

/** Open the follow-up on what is already on record, not on blanks.
 *
 * This is what keeps a recheck from silently clearing an infection sign or a
 * bleeding answer the athlete never revisited: every field starts where the
 * backend has it, and only what they change is changed. */
function answersFromInjury(injury: InjuryFlagRecord): SurfaceFollowUpAnswers {
  const bleeding = injury.bleeding_status ?? null;
  let bleed: BleedAnswer = EMPTY_SURFACE_ANSWERS.bleed;
  if (bleeding === "uncontrolled") {
    bleed = "uncontrolled";
  } else if (injury.drainage === "present") {
    bleed = "leaking";
  } else if (bleeding === "controlled") {
    bleed = "controlled";
  } else if (bleeding === "none") {
    bleed = "no";
  }
  return {
    skin_integrity: injury.skin_integrity ?? EMPTY_SURFACE_ANSWERS.skin_integrity,
    bleed,
    initialBleed: bleed,
    storedDrainage: injury.drainage ?? null,
    infection_signs: [...(injury.infection_signs ?? [])],
    coverable: injury.coverable ?? EMPTY_SURFACE_ANSWERS.coverable,
    friction_or_contact_problem:
      injury.friction_or_contact_problem ?? EMPTY_SURFACE_ANSWERS.friction_or_contact_problem,
  };
}

function surfaceDeclaration(
  flagId: string,
  status: TodayInjuryCheckinStatus,
  answers: SurfaceFollowUpAnswers,
): TodayInjuryDeclaration {
  const bleedFields = BLEED_ANSWER_FIELDS[answers.bleed];
  // The athlete did not revisit the bleeding question, so the drainage already
  // on record still stands. Sending the canonical mapping's drainage here would
  // downgrade a stored "present" to "unknown" on an otherwise untouched recheck
  // — losing a safety signal nobody asked to change.
  const drainageUntouched = answers.bleed === answers.initialBleed && answers.storedDrainage !== null;
  return {
    flag_id: flagId,
    status,
    skin_integrity: answers.skin_integrity,
    infection_signs: answers.infection_signs,
    coverable: answers.coverable,
    // Asked on the way back down as well as the way up. Friction is what holds a
    // closed wound at a local restriction, so a recheck that could not answer it
    // left that restriction — and the severity floor under it — with no way to
    // lift. The form opens pre-filled from the record, so leaving it alone still
    // preserves the stored answer.
    friction_or_contact_problem: answers.friction_or_contact_problem,
    ...bleedFields,
    ...(drainageUntouched ? { drainage: answers.storedDrainage as Drainage } : {}),
  };
}

const INJURY_SEVERITY_OPTIONS: Array<{ value: InjuryFlagSeverity; label: string }> = [
  { value: "mild", label: "Mild" },
  { value: "moderate", label: "Moderate" },
  { value: "severe", label: "Severe" },
];

const BODY_MAP_SEVERITY_BY_FLAG: Record<InjuryFlagSeverity, BodyMapSeverity> = {
  mild: "low",
  moderate: "moderate",
  severe: "high",
};

const BODY_MAP_VISIBILITY_OPTIONS = [
  { value: "shown", label: "Show" },
  { value: "hidden", label: "Hide" },
];

function cycleInjuryFlagSeverity(severity: InjuryFlagSeverity): InjuryFlagSeverity {
  if (severity === "mild") {
    return "moderate";
  }
  if (severity === "moderate") {
    return "severe";
  }
  return "mild";
}

function getInjuryLabel(injury: InjuryFlagRecord): string {
  // Prefer the server-computed label (built from the shared injury synonym
  // logic) so the card matches the reminder and never re-parses raw words.
  const serverLabel = injury.label?.trim();
  if (serverLabel) {
    return serverLabel;
  }
  const raw = injury.body_area?.trim() || injury.description?.trim();
  return normalizeInjuryLabel(raw) || "Injury";
}

function getInjuryType(injury: InjuryFlagRecord): string {
  // Guided intake stores its structured read of the injury in the description
  // (the taxonomy family plus its `family:specific` pair), so the raw field
  // leaks planner vocabulary — "Right shoulder: blister. surface injury.
  // surface injury:blister". The athlete gets the condition and their own
  // words; the routing keys stay internal.
  return resolveInjuryTypeLabel(injury.description, {
    bodyArea: injury.body_area,
    label: injury.label,
  });
}

/**
 * Daily injury check-in. Each open injury can be marked easing / same / worse /
 * resolved (a per-injury update), and new injuries can be added. Writes reconcile
 * the athlete's injury_flags server-side so a resolved injury clears and a new one
 * is tracked — the data the dynamic plan engine will later read. It also feeds the
 * risk watch, so the badge stays live while any injury is open.
 */
export function TodayInjuryManager({
  openInjuries,
  token,
  onRefresh,
}: {
  openInjuries: InjuryFlagRecord[];
  token: string;
  onRefresh: () => Promise<void>;
}) {
  const { showToast } = useToast();
  const [pendingFlagId, setPendingFlagId] = useState<string | null>(null);
  const [selectedStatusByFlagId, setSelectedStatusByFlagId] = useState<
    Partial<Record<string, TodayInjuryCheckinStatus>>
  >({});
  // Clearing an injury removes it from tracking, so it asks for an explicit
  // confirmation first; this holds the flag id awaiting that "are you sure?".
  const [confirmingClearId, setConfirmingClearId] = useState<string | null>(null);
  // A skin injury needs its skin state before a report can be routed — on the
  // way up (worse) and on the way back down (a restricted wound reported easing
  // or the same). This holds the flag id, which report it belongs to, and the
  // answers so far. Nothing is sent — and nothing is marked selected — until it
  // is submitted.
  const [surfaceFollowUpId, setSurfaceFollowUpId] = useState<string | null>(null);
  const [surfaceFollowUpStatus, setSurfaceFollowUpStatus] =
    useState<TodayInjuryCheckinStatus>("worse");
  const [surfaceAnswers, setSurfaceAnswers] = useState<SurfaceFollowUpAnswers>(
    EMPTY_SURFACE_ANSWERS,
  );
  const isSurfaceRecheck = surfaceFollowUpStatus !== "worse";
  const [isAddFormOpen, setIsAddFormOpen] = useState(false);
  const [isAdding, setIsAdding] = useState(false);
  const [newArea, setNewArea] = useState("");
  const [newSeverity, setNewSeverity] = useState<InjuryFlagSeverity>("moderate");
  const [newType, setNewType] = useState<TodayInjuryTypeSelection>(NO_TODAY_INJURY_TYPE);
  const [newDetail, setNewDetail] = useState("");
  // Whether the last edit hit the word/character cap, so the hint can explain the
  // trim instead of a word silently vanishing.
  const [areaLimited, setAreaLimited] = useState(false);
  const [detailLimited, setDetailLimited] = useState(false);
  const [newZone, setNewZone] = useState("");
  const [bodyMapVisibility, setBodyMapVisibility] = useState<"shown" | "hidden">("hidden");
  const [bodyMapSide, setBodyMapSide] = useState<BodyMapSide>("front");
  // Which required answer stopped the last submit attempt. Both the area and
  // the type are required and neither has a default, so a form that only
  // disabled its own submit button left the athlete tapping a dead control
  // with nothing on screen naming what was missing.
  const [addMissing, setAddMissing] = useState<"area" | "type" | null>(null);
  const areaInputRef = useRef<HTMLInputElement>(null);
  const typeGroupRef = useRef<HTMLDivElement>(null);
  const addFormId = useId();
  const addErrorId = useId();
  const bodyMapVisibilityId = useId();
  const newInjurySelections: BodyMapSelection[] = newArea.trim()
    ? [
        {
          zone: newZone || undefined,
          label: newArea.trim(),
          severity: BODY_MAP_SEVERITY_BY_FLAG[newSeverity],
        },
      ]
    : [];

  async function submit(injuries: TodayInjuryDeclaration[]) {
    const response = await submitTodayInjuryCheckin(token, { injuries });
    await onRefresh();
    return response;
  }

  /** Send one per-injury update. The button only reads as selected AFTER the
   * backend confirms it: an optimistic tick on a request that then fails told
   * the athlete their injury was logged when nothing was saved. Returns whether
   * the write succeeded so callers can keep a follow-up open on failure. */
  async function updateInjury(
    flagId: string,
    status: TodayInjuryCheckinStatus,
    declaration?: TodayInjuryDeclaration,
  ): Promise<boolean> {
    if (pendingFlagId) {
      return false;
    }
    setPendingFlagId(flagId);
    try {
      const response = await submit([declaration ?? { flag_id: flagId, status }]);
      setSelectedStatusByFlagId((current) => ({ ...current, [flagId]: status }));
      const previous = openInjuries.find((injury) => injury.id === flagId);
      const updated = response.open_injuries.find((injury) => injury.id === flagId);
      const severityRaised =
        previous && updated
          ? INJURY_SEVERITY_OPTIONS.findIndex((option) => option.value === updated.severity) >
            INJURY_SEVERITY_OPTIONS.findIndex((option) => option.value === previous.severity)
          : false;
      if (status !== "resolved" && updated?.surface_class === "surface_medical_review") {
        showToast(
          severityRaised
            ? `Severity raised to ${updated.severity}. This skin injury needs checking.`
            : "This skin injury needs checking before training.",
          { tone: "info" },
        );
      } else if (status !== "resolved" && updated?.surface_class === "surface_no_contact") {
        showToast("Injury updated. Keep contact off it until the skin is closed and coverable.", {
          tone: "info",
        });
      } else if (
        status !== "resolved" &&
        updated?.surface_class === "surface_local_restriction"
      ) {
        showToast("Injury updated. Protect it from rubbing or contact.", { tone: "info" });
      } else {
        showToast(status === "resolved" ? "Injury cleared." : "Injury updated.", {
          tone: "success",
        });
      }
      return true;
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Injury update failed.", { tone: "error" });
      return false;
    } finally {
      setPendingFlagId(null);
    }
  }

  // "Easing" applies straight away. "Cleared" routes through an inline
  // confirmation because it removes the injury from tracking, and "Worse" on a
  // known skin injury routes through the surface follow-up, because how a wound
  // is worse (open? bleeding? coverable?) is what decides whether anything about
  // today's session actually changes.
  function openSurfaceFollowUp(injury: InjuryFlagRecord, status: TodayInjuryCheckinStatus) {
    setConfirmingClearId(null);
    // Pre-filled with what is on record, so an untouched answer is preserved
    // rather than blanked by the act of rechecking.
    setSurfaceAnswers(answersFromInjury(injury));
    setSurfaceFollowUpStatus(status);
    setSurfaceFollowUpId(injury.id);
  }

  function handleInjuryAction(injury: InjuryFlagRecord, status: TodayInjuryCheckinStatus) {
    // A write is already in flight. updateInjury would refuse this one anyway,
    // but the handler would first tear down whatever follow-up or confirmation
    // is open — so a click on a second row silently discarded the surface
    // answers being filled in on the first. Refuse before touching any state.
    if (pendingFlagId) {
      return;
    }
    if (status === "resolved") {
      setSurfaceFollowUpId(null);
      setConfirmingClearId(injury.id);
      return;
    }
    if (status === "worse" && needsSurfaceFollowUp(injury)) {
      openSurfaceFollowUp(injury, status);
      return;
    }
    // An easing report on a wound that is currently restricting training has to
    // say what the skin is doing now — otherwise the restriction would either
    // stick forever or lift on nothing.
    if (status !== "worse" && needsSurfaceRecheck(injury)) {
      openSurfaceFollowUp(injury, status);
      return;
    }
    // Choosing a different answer abandons any pending confirmation/follow-up.
    setConfirmingClearId(null);
    setSurfaceFollowUpId(null);
    void updateInjury(injury.id, status);
  }

  async function confirmClear(flagId: string) {
    const saved = await updateInjury(flagId, "resolved");
    if (saved) {
      setConfirmingClearId(null);
    }
  }

  async function submitSurfaceFollowUp(flagId: string) {
    const saved = await updateInjury(
      flagId,
      surfaceFollowUpStatus,
      surfaceDeclaration(flagId, surfaceFollowUpStatus, surfaceAnswers),
    );
    if (saved) {
      setSurfaceFollowUpId(null);
    }
  }

  function toggleInfectionSign(value: string) {
    setSurfaceAnswers((current) => ({
      ...current,
      infection_signs: current.infection_signs.includes(value)
        ? current.infection_signs.filter((sign) => sign !== value)
        : [...current.infection_signs, value],
    }));
  }

  async function addInjury(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isAdding) {
      return;
    }
    const area = newArea.trim();
    // A type is a required, explicit choice — an area alone cannot submit a blank
    // report. ("Other" is a valid choice; it just carries no condition word.)
    // Say which answer is missing and put the cursor on it, rather than refusing
    // the submit silently.
    if (!area) {
      setAddMissing("area");
      areaInputRef.current?.focus();
      return;
    }
    if (!newType) {
      setAddMissing("type");
      typeGroupRef.current?.querySelector("button")?.focus();
      return;
    }
    setAddMissing(null);
    setIsAdding(true);
    try {
      const description = composeTodayInjuryDescription({ injuryType: newType, detail: newDetail });
      await submit([
        { body_area: area, description, severity: newSeverity, status: "ongoing" },
      ]);
      setNewArea("");
      setNewSeverity("moderate");
      setNewType(NO_TODAY_INJURY_TYPE);
      setNewDetail("");
      setAreaLimited(false);
      setDetailLimited(false);
      setNewZone("");
      setAddMissing(null);
      setIsAddFormOpen(false);
      showToast("Injury added.", { tone: "success" });
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Could not add injury.", { tone: "error" });
    } finally {
      setIsAdding(false);
    }
  }

  function selectBodyMapZone(zone: string, label: string) {
    const sameZone = newZone === zone;
    setNewZone(zone);
    setAddMissing((current) => (current === "area" ? null : current));
    if (!sameZone || !newArea.trim()) {
      // Body-map labels go through the same cap as typed text so an inserted label
      // can never exceed the limit either.
      const limited = limitInjuryEntryText(label);
      setNewArea(limited);
      setAreaLimited(limited !== label);
    }
    setNewSeverity((current) => (sameZone ? cycleInjuryFlagSeverity(current) : "mild"));
  }

  // Explicit way out of a selection: the map gesture is fully committed to
  // select / raise-severity, so clearing lives here as a visible control rather
  // than a hidden extra tap or long-press.
  function clearBodyMapSelection() {
    setNewArea("");
    setNewZone("");
    setNewSeverity("moderate");
    setNewType(NO_TODAY_INJURY_TYPE);
    setNewDetail("");
    setAreaLimited(false);
    setDetailLimited(false);
    setAddMissing(null);
  }

  return (
    <section id="today-injury" className="today-card today-injury-card" aria-labelledby="today-injury-heading">
      <div className="today-card-head">
        <div>
          <p className="kicker">Injury check-in</p>
          <h2 id="today-injury-heading">Track today&apos;s injuries</h2>
        </div>
      </div>
      {openInjuries.length ? (
        <ul className="today-injury-list">
          {openInjuries.map((injury) => {
            const selectedStatus = selectedStatusByFlagId[injury.id];
            const injuryType = getInjuryType(injury);
            const isPending = pendingFlagId === injury.id;
            // Any in-flight write locks every row's status actions, not just its
            // own. The store refuses concurrent writes, so leaving other rows
            // clickable only offered an action that could not succeed — and that
            // discarded a follow-up in progress on its way to failing.
            const isLockedByOtherWrite = pendingFlagId !== null && !isPending;

            return (
              <li key={injury.id} className="today-injury-item" data-severity={injury.severity}>
                <div className="today-injury-meta">
                  <span className="today-injury-name">
                    <strong>{getInjuryLabel(injury)}</strong>
                    {injuryType ? <small>{injuryType}</small> : null}
                  </span>
                  <span className="badge status-badge-neutral">{injury.severity}</span>
                  {injury.status === "monitoring" ? <span className="badge">Monitoring</span> : null}
                </div>
                <p className="today-field-label today-injury-status-label">How is it today?</p>
                <p className="today-field-hint today-injury-status-hint">
                  Only tap if it changed — we keep tracking it otherwise.
                </p>
                <div
                  className="today-segment-row today-injury-status-row"
                  role="group"
                  aria-label={`Update ${getInjuryLabel(injury)}`}
                >
                  {INJURY_STATUS_ACTIONS.map((action) => {
                    // Selected styling means SAVED, and a confirmed backend
                    // write is the only thing that produces it. An answer that
                    // is still waiting on a confirmation or a follow-up gets a
                    // neutral "pending" outline instead, so nothing ever looks
                    // logged before it is.
                    const isSelected = action.value === selectedStatus;
                    const isAwaitingConfirmation =
                      (confirmingClearId === injury.id && action.value === "resolved") ||
                      (surfaceFollowUpId === injury.id && action.value === surfaceFollowUpStatus);

                    return (
                      <button
                        key={action.value}
                        type="button"
                        className={`today-segment${isSelected ? " today-segment-active" : ""}${
                          isAwaitingConfirmation ? " today-segment-pending" : ""
                        }`}
                        disabled={isPending || isLockedByOtherWrite}
                        // aria-pressed stays false until the backend confirms:
                        // pressed means SAVED. The pending state is announced
                        // separately so a screen-reader user still knows the
                        // answer is captured but not yet written.
                        aria-pressed={isSelected}
                        aria-describedby={
                          isAwaitingConfirmation ? `${injury.id}-pending-hint` : undefined
                        }
                        data-awaiting-confirmation={isAwaitingConfirmation || undefined}
                        onClick={() => handleInjuryAction(injury, action.value)}
                      >
                        {action.label}
                      </button>
                    );
                  })}
                </div>
                {confirmingClearId === injury.id || surfaceFollowUpId === injury.id ? (
                  <p id={`${injury.id}-pending-hint`} className="today-injury-pending-hint">
                    Not saved yet — confirm below.
                  </p>
                ) : null}
                {surfaceFollowUpId === injury.id ? (
                  <div
                    className="today-injury-surface-followup"
                    data-mode={isSurfaceRecheck ? "recheck" : "worse"}
                    role="group"
                    aria-label={
                      isSurfaceRecheck
                        ? `Recheck the ${getInjuryLabel(injury)}`
                        : `How is the ${getInjuryLabel(injury)} worse?`
                    }
                  >
                    <div className="today-injury-followup-head">
                      <p className="today-injury-followup-eyebrow">
                        {isSurfaceRecheck ? "Skin recheck" : "Skin check"}
                        <span aria-hidden="true"> · 5 quick questions</span>
                      </p>
                      <p className="today-injury-confirm-text">
                        {isSurfaceRecheck
                          ? "Quick recheck so we can lift what no longer applies."
                          : "Quick check so we only change what we need to."}
                      </p>
                    </div>
                    <SegmentGroup
                      label={isSurfaceRecheck ? "Is the skin closed now?" : "Is it open or burst?"}
                      value={surfaceAnswers.skin_integrity}
                      options={SKIN_INTEGRITY_OPTIONS}
                      onChange={(value) =>
                        setSurfaceAnswers((current) => ({ ...current, skin_integrity: value }))
                      }
                    />
                    <SegmentGroup
                      label="Bleeding or weeping?"
                      value={surfaceAnswers.bleed}
                      options={BLEED_OPTIONS}
                      onChange={(value) => setSurfaceAnswers((current) => ({ ...current, bleed: value }))}
                      columns={2}
                    />
                    <div className="today-field-group">
                      <p className="today-field-label">Any infection signs?</p>
                      {/* Multi-select, unlike every other control in this panel — say
                          so and keep a live count, so "none picked" reads as an
                          answered question rather than a skipped one. */}
                      <p className="today-field-hint" aria-live="polite">
                        {surfaceAnswers.infection_signs.length
                          ? `${surfaceAnswers.infection_signs.length} selected`
                          : "Tap any that apply — none is fine"}
                      </p>
                      {/* One per row: these labels are the longest in the panel
                          and will not share a line on a phone without being
                          broken across two. */}
                      <div className="today-segment-row today-segment-row-list">
                        {INFECTION_SIGN_OPTIONS.map((option) => {
                          const checked = surfaceAnswers.infection_signs.includes(option.value);
                          return (
                            <button
                              key={option.value}
                              type="button"
                              className={`today-segment today-segment-multi${
                                checked ? " today-segment-active" : ""
                              }`}
                              aria-pressed={checked}
                              onClick={() => toggleInfectionSign(option.value)}
                            >
                              {option.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    <SegmentGroup
                      label="Can it stay covered?"
                      value={surfaceAnswers.coverable}
                      options={COVERABLE_OPTIONS}
                      onChange={(value) =>
                        setSurfaceAnswers((current) => ({ ...current, coverable: value }))
                      }
                    />
                    <SegmentGroup
                      label={
                        isSurfaceRecheck
                          ? "Is rubbing or contact still the problem?"
                          : "Is rubbing or contact the problem?"
                      }
                      value={surfaceAnswers.friction_or_contact_problem}
                      options={FRICTION_OPTIONS}
                      onChange={(value) =>
                        setSurfaceAnswers((current) => ({
                          ...current,
                          friction_or_contact_problem: value,
                        }))
                      }
                    />
                    <div className="today-injury-confirm-actions today-injury-followup-actions">
                      <button
                        type="button"
                        className="today-injury-confirm-yes"
                        disabled={pendingFlagId !== null}
                        onClick={() => void submitSurfaceFollowUp(injury.id)}
                      >
                        {isPending ? "Saving..." : "Save update"}
                      </button>
                      <button
                        type="button"
                        className="today-injury-confirm-cancel"
                        disabled={pendingFlagId !== null}
                        onClick={() => setSurfaceFollowUpId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
                {confirmingClearId === injury.id ? (
                  <div
                    className="today-injury-confirm"
                    role="alertdialog"
                    aria-label={`Clear ${getInjuryLabel(injury)}?`}
                  >
                    <span className="today-injury-confirm-text">
                      Clear this injury? It will be removed from today&apos;s tracking.
                    </span>
                    <div className="today-injury-confirm-actions">
                      <button
                        type="button"
                        className="today-injury-confirm-yes"
                        disabled={pendingFlagId !== null}
                        onClick={() => void confirmClear(injury.id)}
                      >
                        {pendingFlagId === injury.id ? "Clearing..." : "Yes, clear"}
                      </button>
                      <button
                        type="button"
                        className="today-injury-confirm-cancel"
                        disabled={pendingFlagId !== null}
                        onClick={() => setConfirmingClearId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">No injuries are being tracked. Add one below if something is bothering you.</p>
      )}

      <button
        type="button"
        className="today-risk-more today-injury-add-trigger"
        aria-controls={addFormId}
        aria-expanded={isAddFormOpen}
        data-expanded={isAddFormOpen ? "true" : "false"}
        onClick={() => setIsAddFormOpen((current) => !current)}
      >
        <span>
          {isAddFormOpen ? "" : "+ "}
          {openInjuries.length ? "Add another injury" : "Add injury"}
        </span>
        <span className="today-injury-add-chevron" aria-hidden="true" />
      </button>

      <form
        id={addFormId}
        className="today-injury-add"
        hidden={!isAddFormOpen}
        onSubmit={addInjury}
      >
        <div className="today-injury-add-toolbar">
          <p className="today-injury-add-title">Add injury</p>
          <div className="field today-injury-map-control">
            <label htmlFor={bodyMapVisibilityId}>Body map</label>
            <CustomSelect
              id={bodyMapVisibilityId}
              value={bodyMapVisibility}
              options={BODY_MAP_VISIBILITY_OPTIONS}
              placeholder="Body map"
              onChange={(value) => setBodyMapVisibility(value === "hidden" ? "hidden" : "shown")}
            />
          </div>
        </div>
        {bodyMapVisibility === "shown" ? (
          <BodyMap
            side={bodyMapSide}
            selections={newInjurySelections}
            onZoneSelect={selectBodyMapZone}
            onSideChange={setBodyMapSide}
          />
        ) : null}
        {newArea.trim() ? (
          <div className="today-injury-selection" aria-live="polite">
            <span>Selected</span>
            <strong>{newArea.trim()}</strong>
            <button
              type="button"
              className="today-injury-selection-clear"
              onClick={clearBodyMapSelection}
              disabled={isAdding}
              aria-label={`Clear selected area, ${newArea.trim()}`}
            >
              Clear
            </button>
            <small>Tap the same zone to raise severity, or Clear to start over.</small>
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="today-injury-area">
            Where is it?
            <span className="today-field-required">Required</span>
          </label>
          <input
            id="today-injury-area"
            ref={areaInputRef}
            value={newArea}
            spellCheck
            placeholder="e.g. left shoulder"
            aria-invalid={addMissing === "area" || undefined}
            aria-describedby={addMissing === "area" ? addErrorId : undefined}
            onChange={(event) => {
              const raw = event.target.value;
              const value = limitInjuryEntryText(raw);
              setAreaLimited(value !== raw);
              setNewArea(value);
              if (value.trim()) {
                setAddMissing((current) => (current === "area" ? null : current));
              } else {
                setNewZone("");
              }
            }}
          />
          <small
            className="today-injury-limit-hint"
            data-limit-hit={areaLimited}
            aria-live="polite"
          >
            {areaLimited
              ? `${TODAY_INJURY_MAX_WORDS}-word limit — extra removed`
              : `Up to ${TODAY_INJURY_MAX_WORDS} words`}
          </small>
        </div>
        <div ref={typeGroupRef}>
          <SegmentGroup
            label="Type"
            value={newType}
            options={TODAY_INJURY_TYPE_OPTIONS}
            onChange={(value) => {
              setNewType(value);
              setAddMissing((current) => (current === "type" ? null : current));
            }}
            columns={2}
            required
            invalid={addMissing === "type"}
          />
        </div>
        <div className="field today-injury-detail">
          <label htmlFor="today-injury-detail">Anything else? — optional</label>
          <input
            id="today-injury-detail"
            value={newDetail}
            spellCheck
            placeholder="e.g. worse when sprinting"
            onChange={(event) => {
              const raw = event.target.value;
              setDetailLimited(isInjuryEntryLimited(raw));
              setNewDetail(limitInjuryEntryText(raw));
            }}
          />
          <small
            className="today-injury-limit-hint"
            data-limit-hit={detailLimited}
            aria-live="polite"
          >
            {detailLimited
              ? `${TODAY_INJURY_MAX_WORDS}-word limit — extra removed`
              : `Up to ${TODAY_INJURY_MAX_WORDS} words`}
          </small>
        </div>
        <SegmentGroup
          label="Severity"
          value={newSeverity}
          options={INJURY_SEVERITY_OPTIONS}
          onChange={setNewSeverity}
        />
        {addMissing ? (
          <p id={addErrorId} className="today-inline-error" role="alert">
            {addMissing === "area"
              ? "Say where it is first — tap a spot on the body map, or type the area."
              : "Pick a type first. If none of these fit, tap “Other”."}
          </p>
        ) : null}
        {/* Deliberately not disabled on an incomplete form. A disabled submit is
            the reason a missing type read as the app being broken: the only
            feedback was a button that would not respond. Let the tap land, then
            name what is missing. */}
        <button type="submit" className="secondary-button" disabled={isAdding}>
          {isAdding ? "Adding..." : "Add injury"}
        </button>
      </form>
    </section>
  );
}
