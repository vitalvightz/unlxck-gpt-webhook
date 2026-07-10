"use client";

import { type FormEvent, useId, useState } from "react";

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
import { normalizeInjuryLabel } from "@/lib/injury-display";
import type {
  InjuryFlagRecord,
  InjuryFlagSeverity,
  TodayInjuryCheckinStatus,
  TodayInjuryDeclaration,
} from "@/lib/types";

const INJURY_STATUS_ACTIONS: Array<{ value: TodayInjuryCheckinStatus; label: string }> = [
  { value: "improving", label: "Easing" },
  { value: "ongoing", label: "Same" },
  { value: "worse", label: "Worse" },
  { value: "resolved", label: "Cleared" },
];

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
  const [isAdding, setIsAdding] = useState(false);
  const [newArea, setNewArea] = useState("");
  const [newSeverity, setNewSeverity] = useState<InjuryFlagSeverity>("moderate");
  const [newZone, setNewZone] = useState("");
  const [bodyMapVisibility, setBodyMapVisibility] = useState<"shown" | "hidden">("hidden");
  const [bodyMapSide, setBodyMapSide] = useState<BodyMapSide>("front");
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
    await submitTodayInjuryCheckin(token, { injuries });
    await onRefresh();
  }

  async function updateInjury(flagId: string, status: TodayInjuryCheckinStatus) {
    if (pendingFlagId) {
      return;
    }
    setPendingFlagId(flagId);
    setSelectedStatusByFlagId((current) => ({ ...current, [flagId]: status }));
    try {
      await submit([{ flag_id: flagId, status }]);
      showToast(status === "resolved" ? "Injury cleared." : "Injury updated.", {
        tone: "success",
      });
    } catch (error) {
      setSelectedStatusByFlagId((current) => {
        const next = { ...current };
        delete next[flagId];
        return next;
      });
      showToast(error instanceof Error ? error.message : "Injury update failed.", { tone: "error" });
    } finally {
      setPendingFlagId(null);
    }
  }

  // "Easing" / "Same" / "Worse" apply straight away; "Cleared" routes through an
  // inline confirmation because it removes the injury from tracking.
  function handleInjuryAction(flagId: string, status: TodayInjuryCheckinStatus) {
    if (status === "resolved") {
      setConfirmingClearId(flagId);
      return;
    }
    void updateInjury(flagId, status);
  }

  async function confirmClear(flagId: string) {
    await updateInjury(flagId, "resolved");
    setConfirmingClearId(null);
  }

  async function addInjury(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const area = newArea.trim();
    if (!area || isAdding) {
      return;
    }
    setIsAdding(true);
    try {
      await submit([{ body_area: area, severity: newSeverity, status: "ongoing" }]);
      setNewArea("");
      setNewSeverity("moderate");
      setNewZone("");
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
    if (!sameZone || !newArea.trim()) {
      setNewArea(label);
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
            const isPending = pendingFlagId === injury.id;

            return (
              <li key={injury.id} className="today-injury-item" data-severity={injury.severity}>
                <div className="today-injury-meta">
                  <span className="today-injury-name">{getInjuryLabel(injury)}</span>
                  <span className="badge status-badge-neutral">{injury.severity}</span>
                  {injury.status === "monitoring" ? <span className="badge">Monitoring</span> : null}
                </div>
                <div className="today-segment-row" role="group" aria-label={`Update ${getInjuryLabel(injury)}`}>
                  {INJURY_STATUS_ACTIONS.map((action) => {
                    const activeStatus = confirmingClearId === injury.id ? "resolved" : selectedStatus;
                    const isSelected = action.value === activeStatus;

                    return (
                      <button
                        key={action.value}
                        type="button"
                        className={`today-segment${isSelected ? " today-segment-active" : ""}`}
                        disabled={isPending}
                        aria-pressed={isSelected}
                        onClick={() => handleInjuryAction(injury.id, action.value)}
                      >
                        {action.label}
                      </button>
                    );
                  })}
                </div>
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

      <form className="today-injury-add" onSubmit={addInjury}>
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
        <label className="field" htmlFor="today-injury-area">
          <span className="sr-only">Add injury</span>
          <input
            id="today-injury-area"
            value={newArea}
            maxLength={200}
            placeholder="e.g. left shoulder bruise"
            onChange={(event) => {
              const value = event.target.value;
              setNewArea(value);
              if (!value.trim()) {
                setNewZone("");
              }
            }}
          />
        </label>
        <SegmentGroup
          label="Severity"
          value={newSeverity}
          options={INJURY_SEVERITY_OPTIONS}
          onChange={setNewSeverity}
        />
        <button
          type="submit"
          className="secondary-button"
          disabled={isAdding || !newArea.trim()}
        >
          {isAdding ? "Adding..." : "Add injury"}
        </button>
      </form>
    </section>
  );
}
