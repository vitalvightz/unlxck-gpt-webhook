from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    file.write_text(text.replace(old, new, 1))


def append_once(path: str, marker: str, addition: str) -> None:
    file = Path(path)
    text = file.read_text()
    if marker in text:
        return
    file.write_text(text.rstrip() + "\n\n" + addition.strip() + "\n")


replace_once(
    "api/structured_plan_models.py",
    """    purpose: str | None = None
    coaching_cues: list[str] = Field(default_factory=list)
""",
    """    purpose: str | None = None
    why_today: str | None = None
    coaching_cues: list[str] = Field(default_factory=list)
""",
)

replace_once(
    "web/lib/types.ts",
    """  purpose?: string | null;
  coaching_cues?: string[] | null;
""",
    """  purpose?: string | null;
  why_today?: string | null;
  coaching_cues?: string[] | null;
""",
)

replace_once(
    "api/structured_plan_generation.py",
    """def _dedupe_stop_rules(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _strip_stop_rule_label(value)
        key = text.casefold().strip().rstrip(".")
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _normalize_mindset(value: Any) -> dict[str, Any]:
""",
    """def _dedupe_stop_rules(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _strip_stop_rule_label(value)
        key = text.casefold().strip().rstrip(".")
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


_BLOCK_DETAIL_LABEL_RE = re.compile(
    r"^\s*(purpose|why\s+today|easier|regress(?:ion)?|progress(?:ion)?|"
    r"stop(?:\s+rule)?|swaps?|substitutions?)\s*:\s*(.*)$",
    re.IGNORECASE,
)


def _dedupe_text_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _coerce_str(value).strip()
        key = re.sub(r"\s+", " ", text).casefold().rstrip(" .")
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _normalize_mindset(value: Any) -> dict[str, Any]:
""",
)

replace_once(
    "api/structured_plan_generation.py",
    """    # Carry coaching detail through, tolerating a single string instead of a
    # list. An explicit null must also become [] — the schema fields are
    # non-optional lists, so a passed-through None rejects the whole card.
    for list_key in ("coaching_cues", "regression_options", "substitutions", "stop_rules"):
        if list_key in out:
            out[list_key] = _coerce_str_list(out.get(list_key))
    # Late-fight prose occasionally arrives as fake adjustment bullets. Keep
    # stop/safety criteria separate from exercise progression so the athlete
    # never sees a stop condition labelled as Progress.
    cues = _coerce_str_list(out.get("coaching_cues"))
    cleaned_cues: list[str] = []
    stop_cues: list[str] = []
    for cue in cues:
        if re.fullmatch(
            r"\s*(?:progress(?:ion)?\s*/\s*)?regress(?:ion)?\s*(?:/\s*)?\s*",
            cue,
            re.IGNORECASE,
        ):
            continue
        if re.match(r"^\s*stop(?:\s+rule)?\s*:|^\s*stop(?!-)\b", cue, re.IGNORECASE):
            stop_cues.append(cue.strip())
            continue
        cleaned_cues.append(cue)
    if "coaching_cues" in out or cleaned_cues != cues:
        out["coaching_cues"] = cleaned_cues
""",
    """    # Carry coaching detail through, tolerating a single string instead of a
    # list. An explicit null must also become [] — the schema fields are
    # non-optional lists, so a passed-through None rejects the whole card.
    for list_key in ("coaching_cues", "regression_options", "substitutions", "stop_rules"):
        if list_key in out:
            out[list_key] = _coerce_str_list(out.get(list_key))
    for text_key in ("purpose", "why_today"):
        if text_key in out:
            text_value = _coerce_str(out.get(text_key)).strip()
            if text_value:
                out[text_key] = text_value
            else:
                out.pop(text_key, None)

    # Converter/source prose can leak labelled rationale and adjustment lines into
    # coaching_cues. Route each label to its semantic field so the red cue bullets
    # remain strictly about how to execute the exercise.
    cues = _coerce_str_list(out.get("coaching_cues"))
    cleaned_cues: list[str] = []
    stop_cues: list[str] = []
    regression_cues: list[str] = []
    substitution_cues: list[str] = []
    progression_cues: list[str] = []
    for cue in cues:
        if re.fullmatch(
            r"\s*(?:progress(?:ion)?\s*/\s*)?regress(?:ion)?\s*(?:/\s*)?\s*",
            cue,
            re.IGNORECASE,
        ):
            continue
        labelled = _BLOCK_DETAIL_LABEL_RE.match(cue)
        if labelled:
            label = re.sub(r"\s+", " ", labelled.group(1).strip().casefold())
            detail = labelled.group(2).strip()
            if not detail:
                continue
            if label == "purpose":
                out.setdefault("purpose", detail)
            elif label == "why today":
                out.setdefault("why_today", detail)
            elif label in {"easier", "regress", "regression"}:
                regression_cues.append(detail)
            elif label in {"progress", "progression"}:
                progression_cues.append(detail)
            elif label.startswith("stop"):
                stop_cues.append(detail)
            else:
                substitution_cues.append(detail)
            continue
        if re.match(r"^\s*stop(?!-)\b", cue, re.IGNORECASE):
            stop_cues.append(cue.strip())
            continue
        cleaned_cues.append(cue)

    out["coaching_cues"] = _dedupe_text_values(cleaned_cues)
    out["regression_options"] = _dedupe_text_values(
        _coerce_str_list(out.get("regression_options")) + regression_cues
    )
    out["substitutions"] = _dedupe_text_values(
        _coerce_str_list(out.get("substitutions")) + substitution_cues
    )
""",
)

replace_once(
    "api/structured_plan_generation.py",
    """    progression_rule, embedded_stops = _split_progression_and_stop_rules(out.get("progression_rule"))
    stop_rules = _dedupe_stop_rules(
        _coerce_str_list(out.get("stop_rules")) + stop_cues + embedded_stops
    )
    if progression_rule:
        out["progression_rule"] = progression_rule
    else:
        out.pop("progression_rule", None)
""",
    """    progression_rule = ""
    embedded_stops: list[str] = []
    progression_candidates = [
        _coerce_str(out.get("progression_rule")).strip(),
        *progression_cues,
    ]
    for candidate in progression_candidates:
        if not candidate:
            continue
        candidate_progression, candidate_stops = _split_progression_and_stop_rules(candidate)
        embedded_stops.extend(candidate_stops)
        if candidate_progression and not progression_rule:
            progression_rule = candidate_progression
    stop_rules = _dedupe_stop_rules(
        _coerce_str_list(out.get("stop_rules")) + stop_cues + embedded_stops
    )
    if progression_rule:
        out["progression_rule"] = progression_rule
    else:
        out.pop("progression_rule", None)
""",
)

replace_once(
    "api/structured_plan_generation.py",
    """- When the plan states them, carry per-block detail into each block:
  "coaching_cues" (list), "regression_options"/"substitutions" (lists of safer or
  alternative exercises), "progression_rule" (exercise-level advancement only),
  and "stop_rules" (list of stop/safety criteria). progression_rule may be omitted
  when the source gives no genuine exercise progression. Do NOT put taper/week
  dose restrictions, injury restrictions, session-programming constraints, or
  stop criteria into progression_rule unless the text actually says how that
  specific exercise advances.
- Treat "Easier:" / "Regression:" content as regression_options and "Stop:" /
  "Stop rule:" content as stop_rules. Never place those labelled lines in
  coaching_cues or progression_rule. Ignore a bare separator label such as
  "Regression /" rather than rendering it as athlete guidance.
""",
    """- When the plan states them, carry per-block detail into separate semantic fields:
  "purpose" (what the exercise develops), "why_today" (why it is placed today),
  "coaching_cues" (execution-only how-to instructions),
  "regression_options"/"substitutions" (safer or alternative exercises),
  "progression_rule" (exercise-level advancement only), and "stop_rules"
  (stop/safety criteria). Preserve purpose/why_today as structured backend context,
  but NEVER copy those explanations into coaching_cues.
- coaching_cues MUST tell the athlete how to execute the exercise: position,
  movement, intent, brace, rhythm, guard, stance, reset, or other actionable form
  cues. Do NOT put Purpose, Why today, Easier/Regression, Progress/Progression,
  Stop/Stop rule, Swap/Substitution, taper rationale, phase rationale, or selection
  reasoning in coaching_cues.
- Route labelled source lines deterministically: "Purpose:" -> purpose;
  "Why today:" -> why_today; "Easier:" / "Regression:" -> regression_options;
  "Progress:" / "Progression:" -> progression_rule; "Stop:" / "Stop rule:" ->
  stop_rules; "Swap:" / "Swaps:" / "Substitution:" -> substitutions. Ignore a
  bare separator label such as "Regression /" rather than rendering it as athlete
  guidance. progression_rule may be omitted when the source gives no genuine
  exercise progression. Do NOT put taper/week dose restrictions, injury
  restrictions, session-programming constraints, or stop criteria into it.
""",
)

replace_once(
    "api/structured_plan_generation.py",
    """                  "coaching_cues": ["..."], "regression_options": ["..."], "substitutions": ["..."],
                  "progression_rule": "...", "stop_rules": ["..."]
""",
    """                  "purpose": "...", "why_today": "...", "coaching_cues": ["..."],
                  "regression_options": ["..."], "substitutions": ["..."],
                  "progression_rule": "...", "stop_rules": ["..."]
""",
)

replace_once(
    "web/lib/structured-plan.ts",
    """export function getBlockCoachingDisplay(
  block: StructuredBlock | null | undefined,
): { cues: string[]; stopRules: string[] } {
  const cues: string[] = [];
  const stopRules: string[] = [];
  for (const cue of getCoachingCues(block)) {
    if (BARE_ADJUSTMENT_LABEL_RE.test(cue)) {
      continue;
    }
    if (COACHING_STOP_CUE_RE.test(cue)) {
      stopRules.push(cue);
      continue;
    }
    cues.push(cue);
  }
  return { cues, stopRules };
}

""",
    """export function getBlockCoachingDisplay(
  block: StructuredBlock | null | undefined,
): { cues: string[]; stopRules: string[] } {
  const cues: string[] = [];
  const stopRules: string[] = [];
  for (const cue of getCoachingCues(block)) {
    if (BARE_ADJUSTMENT_LABEL_RE.test(cue)) {
      continue;
    }
    if (COACHING_STOP_CUE_RE.test(cue)) {
      stopRules.push(cue);
      continue;
    }
    cues.push(cue);
  }
  return { cues, stopRules };
}

const BLOCK_DETAIL_LABEL_RE =
  /^\s*(purpose|why\s+today|easier|regress(?:ion)?|progress(?:ion)?|stop(?:\s+rule)?|swaps?|substitutions?)\s*:\s*(.*)$/i;
const COACHING_PURE_STOP_RE = /^\s*stop(?!-)\b/i;

function dedupeBlockText(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const text = cleanText(value);
    if (!text) continue;
    const key = text.toLowerCase().replace(/\s+/g, " ").replace(/[.\s]+$/, "");
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(text);
  }
  return result;
}

/** Athlete-facing execution projection. Rich purpose/why-today reasoning stays
 * on the block object, while labelled legacy prose is routed away from cue bullets. */
export function getBlockExecutionDisplay(
  block: StructuredBlock | null | undefined,
): {
  cues: string[];
  stopRules: string[];
  regressions: string[];
  substitutions: string[];
  progressions: string[];
} {
  const cues: string[] = [];
  const stopRules: string[] = [];
  const regressions = getStringList(block?.regression_options);
  const substitutions = getStringList(block?.substitutions);
  const progressions: string[] = [];

  for (const cue of getCoachingCues(block)) {
    if (BARE_ADJUSTMENT_LABEL_RE.test(cue)) continue;
    const labelled = BLOCK_DETAIL_LABEL_RE.exec(cue);
    if (labelled) {
      const label = labelled[1].toLowerCase().replace(/\s+/g, " ");
      const detail = cleanText(labelled[2]);
      if (!detail) continue;
      if (label === "purpose" || label === "why today") continue;
      if (label === "easier" || label === "regress" || label === "regression") {
        regressions.push(detail);
      } else if (label === "progress" || label === "progression") {
        progressions.push(detail);
      } else if (label.startsWith("stop")) {
        stopRules.push(detail);
      } else {
        substitutions.push(detail);
      }
      continue;
    }
    if (COACHING_PURE_STOP_RE.test(cue)) {
      stopRules.push(cue);
      continue;
    }
    cues.push(cue);
  }

  return {
    cues: dedupeBlockText(cues),
    stopRules: dedupeBlockText(stopRules),
    regressions: dedupeBlockText(regressions),
    substitutions: dedupeBlockText(substitutions),
    progressions: dedupeBlockText(progressions),
  };
}

""",
)

replace_once(
    "web/lib/structured-plan.ts",
    """export function getBlockAdjustmentDisplay(
  block: StructuredBlock | null | undefined,
): { progression: string | null; stopRules: string[] } {
  const explicitStops = getStringList(block?.stop_rules);
  const legacyCueStops = getBlockCoachingDisplay(block).stopRules;
  const rawProgression = cleanText(block?.progression_rule);
  let progression: string | null = rawProgression;
  const embeddedStops: string[] = [];

  if (rawProgression) {
    const match = EMBEDDED_STOP_RULE_LABEL_RE.exec(rawProgression);
    if (match) {
      progression = cleanText(rawProgression.slice(0, match.index).replace(/[\s—–\-:;,.]+$/, ""));
      const stop = cleanText(rawProgression.slice(match.index + match[0].length));
      if (stop) {
        embeddedStops.push(stop);
      }
    } else if (isStopRuleText(rawProgression)) {
      progression = null;
      embeddedStops.push(rawProgression);
    }
  }

  if (progression && isProgrammingOnlyProgression(progression)) {
    progression = null;
  }

  return {
    progression,
    stopRules: dedupeStopRules([...explicitStops, ...legacyCueStops, ...embeddedStops]),
  };
}
""",
    """export function getBlockAdjustmentDisplay(
  block: StructuredBlock | null | undefined,
): { progression: string | null; stopRules: string[] } {
  const explicitStops = getStringList(block?.stop_rules);
  const execution = getBlockExecutionDisplay(block);
  const progressionCandidates = [
    cleanText(block?.progression_rule),
    ...execution.progressions,
  ].filter((value): value is string => value !== null);
  let progression: string | null = null;
  const embeddedStops: string[] = [];

  for (const rawProgression of progressionCandidates) {
    let candidate: string | null = rawProgression;
    const match = EMBEDDED_STOP_RULE_LABEL_RE.exec(rawProgression);
    if (match) {
      candidate = cleanText(rawProgression.slice(0, match.index).replace(/[\s—–\-:;,.]+$/, ""));
      const stop = cleanText(rawProgression.slice(match.index + match[0].length));
      if (stop) embeddedStops.push(stop);
    } else if (isStopRuleText(rawProgression)) {
      candidate = null;
      embeddedStops.push(rawProgression);
    }
    if (candidate && isProgrammingOnlyProgression(candidate)) candidate = null;
    if (!progression && candidate) progression = candidate;
  }

  return {
    progression,
    stopRules: dedupeStopRules([
      ...explicitStops,
      ...execution.stopRules,
      ...embeddedStops,
    ]),
  };
}
""",
)

replace_once(
    "web/components/structured-plan-renderer.tsx",
    """  getBlockCoachingDisplay,
  getBlockAdjustmentDisplay,
""",
    """  getBlockExecutionDisplay,
  getBlockAdjustmentDisplay,
""",
)

replace_once(
    "web/components/structured-plan-renderer.tsx",
    """  const purpose = athleteFacingRationale(block.purpose);
  const { cues } = getBlockCoachingDisplay(block);
  const substitutions = getStringList(block.substitutions);
  const regressions = getStringList(block.regression_options);
""",
    """  const { cues, regressions, substitutions } = getBlockExecutionDisplay(block);
""",
)

replace_once(
    "web/components/structured-plan-renderer.tsx",
    """      {purpose ? <p className="sp-block-purpose">{purpose}</p> : null}
""",
    """""",
)

append_once(
    "tests/test_structured_plan_stop_rules.py",
    "test_normalizer_routes_planning_prose_away_from_execution_cues",
    """def test_normalizer_routes_planning_prose_away_from_execution_cues():
    block = _normalize_block(
        {
            "block_id": "band-punch",
            "block_type": "accessory",
            "display_name": "Band-Resisted Punch",
            "coaching_cues": [
                "Purpose: transfer horizontal punching force under slight resistance",
                "Why today: single neural touch without disrupting taper",
                "Explosive intent; accelerate through full range",
                "Easier: reduce band tension",
                "Reset guard immediately",
                "Stop: sharp ankle pain or uncontrolled balance loss",
            ],
            "regression_options": ["Reduce band tension"],
        }
    )
    assert block["purpose"] == "transfer horizontal punching force under slight resistance"
    assert block["why_today"] == "single neural touch without disrupting taper"
    assert block["coaching_cues"] == [
        "Explosive intent; accelerate through full range",
        "Reset guard immediately",
    ]
    assert block["regression_options"] == ["Reduce band tension"]
    assert block["stop_rules"] == ["sharp ankle pain or uncontrolled balance loss"]


def test_converter_prompt_keeps_reasoning_rich_but_cues_execution_only():
    prompt = build_structured_plan_prompt(plan_markdown="D-7 — Band-Resisted Punch")
    assert '"why_today"' in prompt
    assert "execution-only how-to instructions" in prompt
    assert '"Why today:" -> why_today' in prompt
""",
)

replace_once(
    "web/lib/structured-plan-stop-rules.test.ts",
    """import { getBlockAdjustmentDisplay } from "./structured-plan.ts";
""",
    """import { getBlockAdjustmentDisplay, getBlockExecutionDisplay } from "./structured-plan.ts";
""",
)

append_once(
    "web/lib/structured-plan-stop-rules.test.ts",
    "legacy labelled planning prose is hidden from execution cues",
    """test("legacy labelled planning prose is hidden from execution cues", () => {
  assert.deepEqual(
    getBlockExecutionDisplay({
      coaching_cues: [
        "Purpose: transfer horizontal punching force under slight resistance",
        "Why today: single neural touch without disrupting taper",
        "Explosive intent; accelerate through full range",
        "Easier: reduce band tension",
        "Reset guard immediately",
        "Stop: sharp ankle pain",
      ],
      regression_options: ["Reduce band tension"],
    }),
    {
      cues: ["Explosive intent; accelerate through full range", "Reset guard immediately"],
      stopRules: ["sharp ankle pain"],
      regressions: ["Reduce band tension"],
      substitutions: [],
      progressions: [],
    },
  );
});
""",
)

append_once(
    "web/components/structured-plan-stop-rules.test.tsx",
    "exercise card hides planning transcript and deduplicates Easier guidance",
    """test("exercise card hides planning transcript and deduplicates Easier guidance", () => {
  const html = renderToStaticMarkup(
    <BlockCard
      block={{
        block_id: "band-punch",
        block_type: "power",
        display_name: "Band-Resisted Punch",
        purpose: "Low-volume neural strength to preserve punch power and speed.",
        why_today: "Single sharp neural touch in the sharpness week.",
        coaching_cues: [
          "Purpose: maintain punch speed under slight resistance",
          "Why today: keep the dose small in sharpness week",
          "Explosive intent; accelerate through full range",
          "Easier: reduce band tension",
          "Reset guard immediately",
        ],
        regression_options: ["Reduce band tension"],
      }}
    />,
  );

  assert.equal(html.includes("Low-volume neural strength to preserve punch power and speed."), false);
  assert.equal(html.includes("Single sharp neural touch in the sharpness week."), false);
  assert.equal(html.includes("maintain punch speed under slight resistance"), false);
  assert.equal(html.includes("keep the dose small in sharpness week"), false);
  assert.equal(html.includes("Explosive intent; accelerate through full range"), true);
  assert.equal(html.includes("Reset guard immediately"), true);
  assert.equal(html.split("Reduce band tension").length - 1, 1);
});
""",
)
