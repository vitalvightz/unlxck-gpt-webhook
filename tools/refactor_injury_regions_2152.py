from __future__ import annotations

from pathlib import Path
from textwrap import dedent


def write(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dedent(content).lstrip(), encoding="utf-8")


write(
    "fightcamp/injury_body_region.py",
    r'''
    """Broad body-region classification built on the existing injury parser.

    The injury system already owns the large synonym vocabulary in
    ``fightcamp.injury_synonyms.LOCATION_MAP``. This module deliberately does not
    repeat those synonyms. It groups the parser's small set of canonical locations
    into the broad loading regions consumed by Today.
    """

    from __future__ import annotations

    import re
    from typing import Literal, TypedDict

    from .injury_location_registry import build_location_region_map

    BodyRegion = Literal[
        "lower_limb",
        "upper_limb",
        "trunk_spine",
        "head_neck",
        "unknown",
    ]

    RegionGroup = Literal[
        "lower_leg_foot",
        "knee",
        "hip_groin",
        "upper_limb",
        "spine_pelvis",
        "head_face",
        "lower_limb",
        "unknown",
    ]


    class InjuryBodyRegionContext(TypedDict):
        canonical_location: str | None
        region_group: RegionGroup
        body_region: BodyRegion


    # Canonical locations only — never athlete-entered synonyms. Synonym
    # recognition remains owned by LOCATION_MAP/canonicalize_location.
    _CANONICAL_REGION_GROUP: dict[str, RegionGroup] = {
        "toe": "lower_leg_foot",
        "foot": "lower_leg_foot",
        "heel": "lower_leg_foot",
        "ankle": "lower_leg_foot",
        "achilles": "lower_leg_foot",
        "calf": "lower_leg_foot",
        "shin": "lower_leg_foot",
        "hamstring": "lower_leg_foot",
        "quads": "knee",
        "knee": "knee",
        "hip": "hip_groin",
        "hip flexor": "hip_groin",
        "groin": "hip_groin",
        "glute": "hip_groin",
        "glutes": "hip_groin",
        "biceps": "upper_limb",
        "triceps": "upper_limb",
        "shoulder": "upper_limb",
        "elbow": "upper_limb",
        "forearm": "upper_limb",
        "wrist": "upper_limb",
        "hand": "upper_limb",
        "fingers": "upper_limb",
        "chest": "spine_pelvis",
        "core": "spine_pelvis",
        "obliques": "spine_pelvis",
        "upper back": "spine_pelvis",
        "lower back": "spine_pelvis",
        "si joint": "spine_pelvis",
        "neck": "head_face",
        "jaw": "head_face",
        "face": "head_face",
        "eye": "head_face",
    }

    _BODY_REGION_BY_GROUP: dict[str, BodyRegion] = {
        "lower_leg_foot": "lower_limb",
        "knee": "lower_limb",
        "hip_groin": "lower_limb",
        "lower_limb": "lower_limb",
        "upper_limb": "upper_limb",
        "spine_pelvis": "trunk_spine",
        "head_face": "head_neck",
    }

    _FALLBACK_GROUP_BY_REGION: dict[BodyRegion, RegionGroup] = {
        "lower_limb": "lower_limb",
        "upper_limb": "upper_limb",
        "trunk_spine": "spine_pelvis",
        "head_neck": "head_face",
        "unknown": "unknown",
    }

    # Broad anatomical words whose legacy canonical location is intentionally
    # ``unspecified``. These are fallbacks, not a second synonym bank.
    _GENERIC_LOWER_LIMB = re.compile(
        r"\b(?:leg|legs|lower\s+leg|lower\s+legs|femur|thigh\s+bone)\b", re.I
    )
    _GENERIC_UPPER_LIMB = re.compile(
        r"\b(?:arm|arms|upper\s+arm|upper\s+arms)\b", re.I
    )
    _GENERIC_TRUNK_SPINE = re.compile(
        r"\b(?:torso|trunk|spine|spinal|pelvis|pelvic|coccyx|tailbone|ribs?|ribcage|sternum)\b",
        re.I,
    )
    _GENERIC_BACK = re.compile(
        r"\bback\b(?!\s+of\s+(?:leg|thigh|knee|calf|arm|shoulder))", re.I
    )
    _GENERIC_HEAD_NECK = re.compile(r"\b(?:head|brain|skull)\b", re.I)


    def region_group_for_canonical_location(location: object) -> RegionGroup:
        """Return the existing detailed group for one canonical location."""
        normalized = " ".join(
            str(location or "").replace("_", " ").lower().split()
        )
        if not normalized or normalized == "unspecified":
            return "unknown"
        registry_group = build_location_region_map().get(normalized)
        group = registry_group or _CANONICAL_REGION_GROUP.get(normalized)
        if group in _BODY_REGION_BY_GROUP:
            return group  # type: ignore[return-value]
        return "unknown"


    def body_region_for_canonical_location(location: object) -> BodyRegion:
        return _BODY_REGION_BY_GROUP.get(
            region_group_for_canonical_location(location), "unknown"
        )


    def _generic_body_region(text: str) -> BodyRegion:
        if _GENERIC_LOWER_LIMB.search(text):
            return "lower_limb"
        if _GENERIC_UPPER_LIMB.search(text):
            return "upper_limb"
        if _GENERIC_TRUNK_SPINE.search(text) or _GENERIC_BACK.search(text):
            return "trunk_spine"
        if _GENERIC_HEAD_NECK.search(text):
            return "head_neck"
        return "unknown"


    def injury_body_region_context(
        body_area: object,
        description: object,
    ) -> InjuryBodyRegionContext:
        """Resolve an injury through the shared scorer, then group its location."""
        from .injury_scoring import score_injury_phrase
        from .injury_synonyms import canonicalize_location

        text = " ".join(
            part
            for part in (
                str(body_area or "").strip(),
                str(description or "").strip(),
            )
            if part
        )
        score = score_injury_phrase(text) or {}
        canonical = " ".join(
            str(score.get("location") or "").replace("_", " ").lower().split()
        )
        if not canonical or canonical == "unspecified":
            fallback = canonicalize_location(text) if text else None
            canonical = " ".join(
                str(fallback or "").replace("_", " ").lower().split()
            )

        region_group = region_group_for_canonical_location(canonical)
        body_region = _BODY_REGION_BY_GROUP.get(region_group, "unknown")
        canonical_location = (
            canonical if canonical and canonical != "unspecified" else None
        )

        if body_region == "unknown":
            body_region = _generic_body_region(text)
            region_group = _FALLBACK_GROUP_BY_REGION[body_region]

        return {
            "canonical_location": canonical_location,
            "region_group": region_group,
            "body_region": body_region,
        }
    ''',
)

service_path = Path("api/services/today_service.py")
service = service_path.read_text(encoding="utf-8")
import_anchor = "from fightcamp.weekly_schedule_view import normalize_weekday\n"
assert import_anchor in service
service = service.replace(
    import_anchor,
    "from fightcamp.injury_body_region import injury_body_region_context\n"
    + import_anchor,
    1,
)
helper_anchor = "    return rows\n\n\ndef _load_relevant_worse_injury"
helper = '''    return rows


def _with_safe_session_context(
    injuries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Attach backend-owned anatomy and consequence fields for Today.

    The browser must never maintain a second injury synonym parser. Every body
    phrase is resolved by the existing backend injury system, then its canonical
    location is grouped for safe-session loading decisions.
    """
    rows: list[dict[str, Any]] = []
    for injury in injuries or []:
        row = dict(injury)
        try:
            row.update(
                injury_body_region_context(
                    row.get("body_area"), row.get("description")
                )
            )
            row["consequence"] = injury_consequence_tier(
                row.get("body_area"),
                row.get("description"),
                severity=row.get("severity"),
            )
        except Exception:
            logger.exception("[today] safe_session_injury_classification_failed")
            row.setdefault("canonical_location", None)
            row.setdefault("region_group", "unknown")
            row.setdefault("body_region", "unknown")
            row.setdefault("consequence", None)
        rows.append(row)
    return rows


def _load_relevant_worse_injury'''
assert helper_anchor in service
service = service.replace(helper_anchor, helper, 1)

open_block = '''    open_injuries = _with_surface_class(
        _ensure_intake_injury_flags(
            store,
            athlete_id=athlete_id,
            plan_row=plan_row,
            open_flags=_open_injury_flags(store, athlete_id),
        )
    )'''
open_replacement = '''    open_injuries = _with_safe_session_context(
        _with_surface_class(
            _ensure_intake_injury_flags(
                store,
                athlete_id=athlete_id,
                plan_row=plan_row,
                open_flags=_open_injury_flags(store, athlete_id),
            )
        )
    )'''
assert open_block in service
service = service.replace(open_block, open_replacement, 1)
service_path.write_text(service, encoding="utf-8")

types_path = Path("web/lib/types.ts")
types = types_path.read_text(encoding="utf-8")
type_anchor = "  label?: string;\n  severity: InjuryFlagSeverity;"
type_replacement = '''  label?: string;
  /** Backend-owned normalized anatomy. The client must not parse injury text. */
  canonical_location?: string | null;
  region_group?:
    | "lower_leg_foot"
    | "knee"
    | "hip_groin"
    | "lower_limb"
    | "upper_limb"
    | "spine_pelvis"
    | "head_face"
    | "unknown";
  body_region?: "lower_limb" | "upper_limb" | "trunk_spine" | "head_neck" | "unknown";
  consequence?: "neuro" | "structural" | "load_sensitive" | null;
  severity: InjuryFlagSeverity;'''
assert type_anchor in types
types = types.replace(type_anchor, type_replacement, 1)
types_path.write_text(types, encoding="utf-8")

today_path = Path("web/lib/today.ts")
today = today_path.read_text(encoding="utf-8")
safe_start = today.index("// ── Safe-session activity gating")
camp_marker = "/**\n * Today's countdown to the fight"
safe_end = today.index(camp_marker, safe_start)
safe_section = r'''// ── Safe-session activity gating ─────────────────────────────────────────────
// Anatomy and injury consequence are resolved by the backend's shared injury
// system. This module consumes structured fields only; it never carries a second
// body-part synonym list or re-parses athlete-entered injury text.

type InjuryRegion = Exclude<
  NonNullable<InjuryFlagRecord["body_region"]>,
  "unknown"
>;

function isActiveInjury(injury: InjuryFlagRecord): boolean {
  return injury.status === "open" || injury.status === "monitoring";
}

function injuryIsLoadIntolerant(injury: InjuryFlagRecord): boolean {
  return (
    injury.severity === "severe" ||
    injury.consequence === "structural" ||
    injury.consequence === "neuro"
  );
}

function hasLoadIntolerantInjuryInRegion(
  openInjuries: readonly InjuryFlagRecord[] | null | undefined,
  region: InjuryRegion,
): boolean {
  return (openInjuries ?? []).some(
    (injury) =>
      isActiveInjury(injury) &&
      injury.body_region === region &&
      injuryIsLoadIntolerant(injury),
  );
}

function hasUnclassifiedLoadIntolerantInjury(
  openInjuries: readonly InjuryFlagRecord[] | null | undefined,
): boolean {
  return (openInjuries ?? []).some(
    (injury) =>
      isActiveInjury(injury) &&
      (!injury.body_region || injury.body_region === "unknown") &&
      injuryIsLoadIntolerant(injury),
  );
}

/** Whether an active lower-limb injury cannot take gait or pedal load. */
export function hasLoadIntolerantLowerLegInjury(
  openInjuries: readonly InjuryFlagRecord[] | null | undefined,
): boolean {
  return hasLoadIntolerantInjuryInRegion(openInjuries, "lower_limb");
}

function hasNeuroDownregulationInjury(
  openInjuries: readonly InjuryFlagRecord[] | null | undefined,
): boolean {
  return (openInjuries ?? []).some(
    (injury) =>
      isActiveInjury(injury) &&
      (injury.consequence === "neuro" ||
        (injury.body_region === "head_neck" && injuryIsLoadIntolerant(injury))),
  );
}

type SafeSessionPosture = "rest_only" | "downregulate" | "standard";

function resolveSafeSessionPosture(
  openInjuries?: readonly InjuryFlagRecord[] | null,
): SafeSessionPosture {
  // A structural/severe injury whose anatomy could not be classified is never a
  // green light for generic movement. Fail closed rather than guessing a limb.
  if (
    hasUnclassifiedLoadIntolerantInjury(openInjuries) ||
    hasLoadIntolerantInjuryInRegion(openInjuries, "trunk_spine")
  ) {
    return "rest_only";
  }
  if (hasNeuroDownregulationInjury(openInjuries)) {
    return "downregulate";
  }
  return "standard";
}

export function resolveSafeSessionAllowed(
  openInjuries?: readonly InjuryFlagRecord[] | null,
): string[] {
  const posture = resolveSafeSessionPosture(openInjuries);
  if (posture === "rest_only") {
    return ["Breathing reset", "Clinician-approved rehab"];
  }
  if (posture === "downregulate") {
    return ["Easy mobility", "Breathing reset", "Clinician-approved rehab"];
  }

  const lowerBlocked = hasLoadIntolerantLowerLegInjury(openInjuries);
  const upperBlocked = hasLoadIntolerantInjuryInRegion(openInjuries, "upper_limb");

  let conditioning: string | null;
  if (lowerBlocked && upperBlocked) {
    conditioning = null;
  } else if (lowerBlocked) {
    conditioning = "Seated upper-body cardio — only if pain-free and available";
  } else {
    conditioning = "Light bike or walk";
  }

  const allowed = ["Easy mobility"];
  if (conditioning) {
    allowed.push(conditioning);
  }
  allowed.push("Breathing reset", "Gentle activation", "Coach-approved rehab");
  return allowed;
}

export function resolveSafeSessionBlocked(
  openInjuries?: readonly InjuryFlagRecord[] | null,
): string[] {
  const lowerBlocked = hasLoadIntolerantLowerLegInjury(openInjuries);
  const upperBlocked = hasLoadIntolerantInjuryInRegion(openInjuries, "upper_limb");
  const trunkBlocked = hasLoadIntolerantInjuryInRegion(openInjuries, "trunk_spine");
  const neuro = hasNeuroDownregulationInjury(openInjuries);
  const unclassified = hasUnclassifiedLoadIntolerantInjury(openInjuries);

  let explosive: string;
  if (unclassified || (upperBlocked && lowerBlocked)) {
    explosive = "Plyos or explosive work";
  } else if (upperBlocked) {
    explosive = "Plyos or explosive upper-body work";
  } else {
    explosive = "Plyos or explosive lower-body work";
  }

  const blocked = ["Sparring", "Hard pads", "HIIT", "Heavy lifting", explosive];
  if (upperBlocked) {
    blocked.push("Overhead or pressing work");
  }
  if (trunkBlocked) {
    blocked.push("Loaded rotation or bracing");
  }
  if (neuro) {
    blocked.push("Head impact or contact drills");
  }
  if (unclassified) {
    blocked.push("Loaded movement");
  }
  return blocked;
}

const SAFE_SESSION_POSTURE_DETAIL: Record<SafeSessionPosture, string> = {
  rest_only:
    "Protect the injured area and let it settle — no loaded movement today, and follow your clinician on what is safe.",
  downregulate:
    "Keep everything calm and symptom-free today — no exertion, and follow your clinician before adding work back.",
  standard: "Protect freshness, reduce risk, and keep the body moving without adding stress.",
};

/**
 * The recovery-only session shown in place of scheduled work when today is a STOP.
 * The backend classifies each active injury; this display only applies the supplied
 * broad region and consequence fields.
 */
export function getSafeSessionView(
  blockedSessionName?: string,
  openInjuries?: readonly InjuryFlagRecord[] | null,
): SafeSessionView {
  const name = (blockedSessionName ?? "").trim();
  const blockedLead =
    name && name.toLowerCase() !== "today's session"
      ? `${name} is blocked today.`
      : "Hard combat work is blocked today.";
  const posture = resolveSafeSessionPosture(openInjuries);
  return {
    eyebrow: "Today's safe session",
    title: posture === "rest_only" ? "Rest and recover" : "Recovery / mobility only",
    detail: `${blockedLead} ${SAFE_SESSION_POSTURE_DETAIL[posture]}`,
    allowed: resolveSafeSessionAllowed(openInjuries),
    blocked: resolveSafeSessionBlocked(openInjuries),
  };
}

'''
today = today[:safe_start] + safe_section + today[safe_end:]
today_path.write_text(today, encoding="utf-8")

test_path = Path("web/lib/today.test.ts")
test_text = test_path.read_text(encoding="utf-8")
old_helper = '''function makeInjury(overrides: Partial<InjuryFlagRecord> = {}): InjuryFlagRecord {
  return {
    id: "inj-1",
    athlete_id: "ath-1",
    source: "checkin",
    body_area: "chest",
    description: "chest bruise",
    label: "Chest bruise",
    severity: "severe",
    status: "open",
    created_at: "2026-07-06T00:00:00Z",
    updated_at: "2026-07-06T00:00:00Z",
    ...overrides,
  };
}'''
new_helper = r'''function makeInjury(overrides: Partial<InjuryFlagRecord> = {}): InjuryFlagRecord {
  // Production receives these fields from the backend. This fixture mirrors that
  // payload so safe-session tests exercise structured context rather than parsing.
  const bodyArea = overrides.body_area ?? "chest";
  const description = overrides.description ?? "chest bruise";
  const text = `${bodyArea} ${description}`.toLowerCase();
  const bodyRegion =
    overrides.body_region ??
    (/\b(?:calf|achilles|ankle|knee|shin|hip|quad|hamstring|leg)\b/.test(text)
      ? "lower_limb"
      : /\b(?:bicep|wrist|arm|shoulder|elbow|hand)\b/.test(text)
        ? "upper_limb"
        : /\b(?:head|neck|brain|skull)\b/.test(text)
          ? "head_neck"
          : /\b(?:back|spine|rib|chest|sternum)\b/.test(text)
            ? "trunk_spine"
            : "unknown");
  const deniedStructural = /\b(?:no|not|ruled out|nothing is)\s+(?:fracture|tear|rupture)/.test(text);
  const consequence =
    overrides.consequence !== undefined
      ? overrides.consequence
      : !deniedStructural && /\b(?:fracture|fractures|rupture|ruptures|tear|tears|torn|dislocation|dislocations|avulsion)\b/.test(text)
        ? "structural"
        : null;
  return {
    id: "inj-1",
    athlete_id: "ath-1",
    source: "checkin",
    body_area: bodyArea,
    description,
    label: "Chest bruise",
    body_region: bodyRegion,
    consequence,
    severity: "severe",
    status: "open",
    created_at: "2026-07-06T00:00:00Z",
    updated_at: "2026-07-06T00:00:00Z",
    ...overrides,
  };
}'''
assert old_helper in test_text
test_text = test_text.replace(old_helper, new_helper, 1)
test_text = test_text.replace(
    '["Easy mobility", "Breathing reset", "Coach-approved rehab"]',
    '["Easy mobility", "Breathing reset", "Clinician-approved rehab"]',
)
test_text = test_text.replace(
    '["Breathing reset", "Coach-approved rehab"]',
    '["Breathing reset", "Clinician-approved rehab"]',
)
test_path.write_text(test_text, encoding="utf-8")

write(
    "tests/test_injury_body_region.py",
    r'''
    from __future__ import annotations

    import pytest

    from api.services.today_service import _with_safe_session_context
    from fightcamp.injury_body_region import (
        body_region_for_canonical_location,
        injury_body_region_context,
        region_group_for_canonical_location,
    )
    from fightcamp.injury_synonyms import LOCATION_MAP


    @pytest.mark.parametrize(
        ("phrase", "canonical", "region"),
        [
            ("soleus tear", "calf", "lower_limb"),
            ("metatarsal fracture", "foot", "lower_limb"),
            ("humerus fracture", "biceps", "upper_limb"),
            ("adductors tear", "groin", "lower_limb"),
            ("forehead cut", "face", "head_neck"),
            ("sternum fracture", "chest", "trunk_spine"),
            ("long head of biceps tear", "biceps", "upper_limb"),
            ("back of knee tear", "knee", "lower_limb"),
        ],
    )
    def test_existing_synonyms_resolve_to_broad_regions(
        phrase: str, canonical: str, region: str
    ) -> None:
        context = injury_body_region_context(phrase, phrase)
        assert context["canonical_location"] == canonical
        assert context["body_region"] == region


    @pytest.mark.parametrize(
        ("phrase", "region"),
        [
            ("femur fracture", "lower_limb"),
            ("leg fracture", "lower_limb"),
            ("arm fracture", "upper_limb"),
            ("spine fracture", "trunk_spine"),
            ("head injury", "head_neck"),
        ],
    )
    def test_generic_backend_locations_receive_conservative_regions(
        phrase: str, region: str
    ) -> None:
        assert injury_body_region_context(phrase, phrase)["body_region"] == region


    def test_every_canonical_location_from_existing_synonym_map_is_grouped() -> None:
        canonicals = {
            " ".join(str(location).replace("_", " ").lower().split())
            for location in LOCATION_MAP.values()
            if str(location).strip() and str(location).strip() != "unspecified"
        }
        missing = {
            location
            for location in canonicals
            if region_group_for_canonical_location(location) == "unknown"
            or body_region_for_canonical_location(location) == "unknown"
        }
        assert missing == set()


    def test_today_payload_enrichment_uses_backend_region_and_consequence() -> None:
        [row] = _with_safe_session_context(
            [
                {
                    "id": "inj-1",
                    "body_area": "soleus",
                    "description": "soleus tear",
                    "severity": "moderate",
                    "status": "open",
                }
            ]
        )
        assert row["canonical_location"] == "calf"
        assert row["region_group"] == "lower_leg_foot"
        assert row["body_region"] == "lower_limb"
        assert row["consequence"] == "structural"
    ''',
)

write(
    "web/lib/today-region.test.ts",
    r'''
    import test from "node:test";
    import assert from "node:assert/strict";

    import { getSafeSessionView } from "./today.ts";
    import type { InjuryFlagRecord } from "./types.ts";

    function injury(overrides: Partial<InjuryFlagRecord>): InjuryFlagRecord {
      return {
        id: "inj-1",
        athlete_id: "ath-1",
        source: "checkin",
        body_area: "",
        description: "",
        severity: "moderate",
        status: "open",
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
        ...overrides,
      };
    }

    test("safe session consumes backend regions for existing deep synonyms", () => {
      for (const [canonical_location, label, region_group] of [
        ["calf", "Soleus tear", "lower_leg_foot"],
        ["foot", "Metatarsal fracture", "lower_leg_foot"],
        ["groin", "Adductors tear", "hip_groin"],
      ] as const) {
        const view = getSafeSessionView("Technical sparring", [
          injury({
            label,
            canonical_location,
            region_group,
            body_region: "lower_limb",
            consequence: "structural",
          }),
        ]);
        assert.equal(view.allowed.includes("Light bike or walk"), false, label);
        assert.equal(
          view.allowed.includes("Seated upper-body cardio — only if pain-free and available"),
          true,
          label,
        );
      }
    });

    test("structured lower- and upper-limb injuries remove every cardio option", () => {
      const view = getSafeSessionView("Technical sparring", [
        injury({ body_region: "lower_limb", consequence: "structural", label: "Ankle fracture" }),
        injury({ id: "inj-2", body_region: "upper_limb", consequence: "structural", label: "Humerus fracture" }),
      ]);
      assert.equal(view.allowed.some((item) => item.toLowerCase().includes("cardio")), false);
    });

    test("trunk and neuro postures use clinician-owned rehab copy", () => {
      const trunk = getSafeSessionView("Technical sparring", [
        injury({ body_region: "trunk_spine", consequence: "structural", label: "Spinal fracture" }),
      ]);
      assert.deepEqual(trunk.allowed, ["Breathing reset", "Clinician-approved rehab"]);
      assert.equal(trunk.title, "Rest and recover");

      const neuro = getSafeSessionView("Technical sparring", [
        injury({ body_region: "head_neck", consequence: "neuro", label: "Concussion" }),
      ]);
      assert.deepEqual(neuro.allowed, [
        "Easy mobility",
        "Breathing reset",
        "Clinician-approved rehab",
      ]);
    });

    test("an unclassified structural injury fails closed", () => {
      const view = getSafeSessionView("Technical sparring", [
        injury({ body_region: "unknown", consequence: "structural", label: "Structural injury" }),
      ]);
      assert.deepEqual(view.allowed, ["Breathing reset", "Clinician-approved rehab"]);
      assert.equal(view.blocked.includes("Loaded movement"), true);
    });

    test("a mild load-sensitive lower-limb injury keeps light conditioning", () => {
      const view = getSafeSessionView("Technical sparring", [
        injury({
          body_region: "lower_limb",
          consequence: "load_sensitive",
          severity: "mild",
          label: "Patellar tendinopathy",
        }),
      ]);
      assert.equal(view.allowed.includes("Light bike or walk"), true);
    });
    ''',
)

for temporary in (
    Path(".github/workflows/refactor-injury-regions-2152.yml"),
    Path("tools/refactor_injury_regions_2152.py"),
):
    if temporary.exists():
        temporary.unlink()
