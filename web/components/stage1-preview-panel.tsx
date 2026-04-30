"use client";

import { useMemo, useState, type ReactNode } from "react";

import type { Stage1PreviewResponse } from "@/lib/types";

type JsonRecord = Record<string, unknown>;

type Stage1AuditItem = {
  key: string;
  phase: string;
  slotGroup: string;
  slotId: string;
  role: string;
  purpose: string;
  name: string;
  why: string;
  score: number | null;
  penalties: number | null;
  restrictionHits: number | null;
  lateWindowAdjustment: number | null;
  reasonCodes: string[];
  alternates: string[];
};

type PreviewView = "audit" | "draft" | "raw";

function isRecord(value: unknown): value is JsonRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item).trim()).filter(Boolean);
}

function humanizeToken(value: string): string {
  const normalized = value.replace(/_/g, " ").trim();
  return normalized ? normalized.charAt(0).toUpperCase() + normalized.slice(1) : "";
}

function selectedItemName(value: unknown): string {
  return isRecord(value) ? readString(value.name) : "";
}

function collectStage1Audit(preview: Stage1PreviewResponse): Stage1AuditItem[] {
  const payload = preview.stage2_payload;
  const candidatePools = isRecord(payload) && isRecord(payload.candidate_pools)
    ? payload.candidate_pools
    : null;
  if (!candidatePools) {
    return [];
  }

  const items: Stage1AuditItem[] = [];
  for (const [phase, phaseValue] of Object.entries(candidatePools)) {
    if (!isRecord(phaseValue)) {
      continue;
    }

    for (const [slotGroup, slotsValue] of Object.entries(phaseValue)) {
      if (!Array.isArray(slotsValue)) {
        continue;
      }

      slotsValue.forEach((slotValue, index) => {
        if (!isRecord(slotValue) || !isRecord(slotValue.selected)) {
          return;
        }

        const selected = slotValue.selected;
        const scoreEvidence: JsonRecord = isRecord(selected.score_evidence) ? selected.score_evidence : {};
        const reasonCodes = readStringArray(selected.reason_codes);
        const evidenceReasonCodes = readStringArray(scoreEvidence.reason_codes);
        const alternates = Array.isArray(slotValue.alternates)
          ? slotValue.alternates.map(selectedItemName).filter(Boolean)
          : [];

        items.push({
          key: `${phase}-${slotGroup}-${readString(slotValue.slot_id) || index}`,
          phase,
          slotGroup,
          slotId: readString(slotValue.slot_id),
          role: readString(slotValue.role),
          purpose: readString(slotValue.purpose),
          name: readString(selected.name) || "Unnamed selection",
          why: readString(selected.why) || readString(selected.explanation) || readString(slotValue.purpose),
          score: readNumber(selected.score) ?? readNumber(scoreEvidence.score),
          penalties: readNumber(selected.penalties) ?? readNumber(scoreEvidence.penalties),
          restrictionHits: readNumber(selected.restriction_hits) ?? readNumber(scoreEvidence.restriction_hits),
          lateWindowAdjustment:
            readNumber(selected.late_window_adjustment) ?? readNumber(scoreEvidence.late_window_adjustment),
          reasonCodes: reasonCodes.length ? reasonCodes : evidenceReasonCodes,
          alternates,
        });
      });
    }
  }

  return items;
}

function buildPreviewArtifact(preview: Stage1PreviewResponse): string {
  return JSON.stringify(
    {
      status: preview.status,
      generated_at: preview.generated_at,
      stage2_skipped: preview.stage2_skipped,
      why_log: preview.why_log,
      planning_brief: preview.planning_brief,
      stage2_payload: preview.stage2_payload,
      parsing_metadata: preview.parsing_metadata,
      coach_notes: preview.coach_notes,
      stage2_handoff_text: preview.stage2_handoff_text,
    },
    null,
    2,
  );
}

function CopyButton({
  text,
  children,
}: {
  text: string;
  children: ReactNode;
}) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  if (!text.trim()) {
    return null;
  }

  return (
    <button type="button" className="ghost-button" onClick={handleCopy}>
      {copied ? "Copied" : children}
    </button>
  );
}

export function Stage1PreviewPanel({
  preview,
  onClear,
}: {
  preview: Stage1PreviewResponse;
  onClear?: () => void;
}) {
  const [activeView, setActiveView] = useState<PreviewView>("audit");
  const auditItems = useMemo(() => collectStage1Audit(preview), [preview]);
  const rawArtifact = useMemo(() => buildPreviewArtifact(preview), [preview]);
  const generatedAt = new Date(preview.generated_at).toLocaleString();

  return (
    <section id="stage1-preview" className="stage1-preview-panel">
      <div className="stage1-preview-header">
        <div className="stage1-preview-title">
          <p className="kicker">Stage 1 preview</p>
          <h2>Planner output before Stage 2</h2>
          <p className="muted">
            Generated {generatedAt}. This run stopped after Stage 1, so no Stage 2 model call was made.
          </p>
        </div>
        <div className="stage1-preview-badges">
          <span className="badge status-badge-success">{humanizeToken(preview.status)}</span>
          <span className="badge status-badge-neutral">Stage 2 skipped</span>
        </div>
      </div>

      <div className="stage1-preview-toolbar">
        <div className="stage1-preview-tabs" role="tablist" aria-label="Stage 1 preview views">
          <button
            type="button"
            role="tab"
            aria-selected={activeView === "audit"}
            className="stage1-preview-tab"
            data-active={activeView === "audit"}
            onClick={() => setActiveView("audit")}
          >
            Selection audit
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeView === "draft"}
            className="stage1-preview-tab"
            data-active={activeView === "draft"}
            onClick={() => setActiveView("draft")}
          >
            Draft text
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeView === "raw"}
            className="stage1-preview-tab"
            data-active={activeView === "raw"}
            onClick={() => setActiveView("raw")}
          >
            Raw artifacts
          </button>
        </div>
        <div className="plan-summary-actions">
          <CopyButton text={preview.plan_text}>Copy draft</CopyButton>
          <CopyButton text={rawArtifact}>Copy raw JSON</CopyButton>
          {onClear ? (
            <button type="button" className="ghost-button" onClick={onClear}>
              Clear
            </button>
          ) : null}
        </div>
      </div>

      {activeView === "audit" ? (
        <div className="stage1-audit-view">
          {auditItems.length ? (
            <div className="stage1-audit-list">
              {auditItems.map((item) => (
                <article key={item.key} className="stage1-audit-item">
                  <div className="stage1-audit-item-header">
                    <div>
                      <p className="kicker">
                        {item.phase} / {humanizeToken(item.slotGroup)}
                      </p>
                      <h3>{item.name}</h3>
                    </div>
                    <span className="badge status-badge-neutral">
                      {item.score === null ? "No score" : `Score ${item.score}`}
                    </span>
                  </div>
                  <p className="muted">
                    {[item.role, item.purpose, item.slotId].filter(Boolean).join(" | ") || "No slot metadata saved."}
                  </p>
                  {item.why ? <p className="stage1-audit-why">{item.why}</p> : null}
                  <div className="stage1-audit-evidence">
                    <span>Penalties: {item.penalties ?? 0}</span>
                    <span>Restriction hits: {item.restrictionHits ?? 0}</span>
                    <span>Late-window adjustment: {item.lateWindowAdjustment ?? 0}</span>
                  </div>
                  {item.reasonCodes.length ? (
                    <div className="stage1-audit-tags">
                      {item.reasonCodes.map((code) => (
                        <span key={code} className="badge status-badge-neutral">
                          {humanizeToken(code)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                  {item.alternates.length ? (
                    <p className="muted">Alternates: {item.alternates.join(", ")}</p>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <div className="support-panel">
              <div className="form-section-header">
                <p className="kicker">Selection audit</p>
                <h3>No candidate pools were emitted</h3>
              </div>
              <p className="muted">
                This Stage 1 result did not include candidate pools. Open Raw artifacts to inspect the saved reason log,
                planning brief, and parser metadata directly.
              </p>
            </div>
          )}
        </div>
      ) : null}

      {activeView === "draft" ? (
        <pre className="plan-text-block">{preview.plan_text || "No Stage 1 draft text returned."}</pre>
      ) : null}

      {activeView === "raw" ? (
        <pre className="code-block">{rawArtifact}</pre>
      ) : null}
    </section>
  );
}
