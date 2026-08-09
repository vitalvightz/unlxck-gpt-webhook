from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    file.write_text(text.replace(old, new, 1))


# Backend schema: stop rules are a first-class block field.
replace_once(
    "api/structured_plan_models.py",
    """    coaching_cues: list[str] = Field(default_factory=list)\n    regression_options: list[str] = Field(default_factory=list)\n    progression_rule: str | None = None\n    substitutions: list[str] = Field(default_factory=list)\n""",
    """    coaching_cues: list[str] = Field(default_factory=list)\n    regression_options: list[str] = Field(default_factory=list)\n    progression_rule: str | None = None\n    stop_rules: list[str] = Field(default_factory=list)\n    substitutions: list[str] = Field(default_factory=list)\n""",
)

# Frontend type contract mirrors the backend field.
replace_once(
    "web/lib/types.ts",
    """  coaching_cues?: string[] | null;\n  regression_options?: string[] | null;\n  substitutions?: string[] | null;\n  progression_rule?: string | null;\n""",
    """  coaching_cues?: string[] | null;\n  regression_options?: string[] | null;\n  substitutions?: string[] | null;\n  progression_rule?: string | null;\n  stop_rules?: string[] | null;\n""",
)

# Backend normalization: split Stop rules from progression and drop programming-only taper text.
generation_path = Path("api/structured_plan_generation.py")
generation = generation_path.read_text()
marker = "def _normalize_mindset(value: Any) -> dict[str, Any]:\n"
helpers = r'''_STOP_RULE_LABEL_RE = re.compile(r"\bstop(?:\s+rule)?\s*:\s*", re.IGNORECASE)
_PURE_STOP_RULE_RE = re.compile(r"^\s*stop(?!-)\b", re.IGNORECASE)
_PROGRAMMING_ONLY_PROGRESSION_RE = re.compile(
    r"^\s*(?:maintain(?:\s+(?:the|this))?\s+dose|keep\s+(?:the\s+)?dose\s+small|"
    r"do\s+not\s+(?:add|increase)\s+(?:sets?|volume)|no\s+(?:set|volume)\s+increase)\b",
    re.IGNORECASE,
)
_POSITIVE_PROGRESSION_RE = re.compile(
    r"\b(?:progress|advance|increase|raise|build|extend|heavier|more\s+resistance|reduce\s+assistance)\b",
    re.IGNORECASE,
)
_NEGATED_PROGRESSION_RE = re.compile(
    r"\b(?:do\s+not|don't|never)\s+(?:add|increase|progress|advance|raise|build|extend)\b",
    re.IGNORECASE,
)


def _strip_stop_rule_label(text: str) -> str:
    return re.sub(r"^\s*stop(?:\s+rule)?\s*:\s*", "", text, flags=re.IGNORECASE).strip()


def _is_programming_only_progression(text: str) -> bool:
    """True for taper/week dose constraints that do not advance the exercise."""
    clean = text.strip()
    if not clean:
        return False
    if _NEGATED_PROGRESSION_RE.search(clean):
        return bool(
            _PROGRAMMING_ONLY_PROGRESSION_RE.search(clean)
            or re.search(r"\b(?:taper|fight[ -]?week|sharpness|freshness)\b", clean, re.IGNORECASE)
        )
    if _POSITIVE_PROGRESSION_RE.search(clean):
        return False
    return bool(_PROGRAMMING_ONLY_PROGRESSION_RE.search(clean))


def _split_progression_and_stop_rules(value: Any) -> tuple[str, list[str]]:
    """Separate a legacy mixed progression string from labelled stop criteria."""
    text = _coerce_str(value).strip()
    if not text:
        return "", []
    match = _STOP_RULE_LABEL_RE.search(text)
    if match:
        progression = text[: match.start()].rstrip(" \t—–-:;,.")
        stop = text[match.end() :].strip()
        stops = [stop] if stop else []
        if progression and _is_programming_only_progression(progression):
            progression = ""
        return progression, stops
    if _PURE_STOP_RULE_RE.search(text):
        return "", [_strip_stop_rule_label(text)]
    if _is_programming_only_progression(text):
        return "", []
    return text, []


def _dedupe_stop_rules(values: list[str]) -> list[str]:
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


'''
if marker not in generation:
    raise SystemExit("structured_plan_generation.py: helper insertion marker missing")
generation = generation.replace(marker, helpers + marker, 1)

old_block = '''    # Carry coaching detail through, tolerating a single string instead of a
    # list. An explicit null must also become [] — the schema fields are
    # non-optional lists, so a passed-through None rejects the whole card.
    for list_key in ("coaching_cues", "regression_options", "substitutions"):
        if list_key in out:
            out[list_key] = _coerce_str_list(out.get(list_key))
    # Late-fight prose occasionally arrives as two fake cue bullets:
    # ``Regression /`` and ``Stop: ...``. The former is only a dangling source
    # label; the latter belongs in progression_rule so the card renders it as a
    # labelled stop instruction rather than ordinary coaching.
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
        if re.match(r"^\s*stop(?:\s+rule)?\s*:", cue, re.IGNORECASE):
            stop_cues.append(cue.strip())
            continue
        cleaned_cues.append(cue)
    if "coaching_cues" in out or cleaned_cues != cues:
        out["coaching_cues"] = cleaned_cues
    if "red_flags" in out:
        out["red_flags"] = [_normalize_red_flag(rule) for rule in _as_dict_list(out.get("red_flags"))]
    if "effort" in out:
        out["effort"] = _normalize_effort(out.get("effort"))
    progression_rule = _coerce_str(out.get("progression_rule")).strip()
    if stop_cues:
        stop_text = " ".join(stop_cues)
        if not progression_rule:
            progression_rule = stop_text
        elif stop_text.lower() not in progression_rule.lower():
            progression_rule = f"{progression_rule.rstrip('.')} — {stop_text}"
    if out.get("progression_rule") is not None or progression_rule:
        out["progression_rule"] = progression_rule
    return out
'''
new_block = '''    # Carry coaching detail through, tolerating a single string instead of a
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
    if "red_flags" in out:
        out["red_flags"] = [_normalize_red_flag(rule) for rule in _as_dict_list(out.get("red_flags"))]
    if "effort" in out:
        out["effort"] = _normalize_effort(out.get("effort"))

    progression_rule, embedded_stops = _split_progression_and_stop_rules(out.get("progression_rule"))
    stop_rules = _dedupe_stop_rules(
        _coerce_str_list(out.get("stop_rules")) + stop_cues + embedded_stops
    )
    if progression_rule:
        out["progression_rule"] = progression_rule
    else:
        out.pop("progression_rule", None)
    if stop_rules or "stop_rules" in out:
        out["stop_rules"] = stop_rules
    return out
'''
if generation.count(old_block) != 1:
    raise SystemExit(f"structured_plan_generation.py: normalize block match count {generation.count(old_block)}")
generation = generation.replace(old_block, new_block, 1)

replace_rules = [
    (
        '''- List fields (coaching_cues, regression_options, substitutions, applies_to)
  MUST be JSON arrays — emit [] when empty, never null and never a bare string.
''',
        '''- List fields (coaching_cues, regression_options, substitutions, stop_rules, applies_to)
  MUST be JSON arrays — emit [] when empty, never null and never a bare string.
''',
    ),
    (
        '''- When the plan states them, carry per-block detail into each block:
  "coaching_cues" (list), "regression_options"/"substitutions" (lists of safer or
  alternative exercises the plan offers), and "progression_rule" (how to advance).
- Treat "Easier:" / "Regression:" content as regression_options and "Stop:" /
  "Stop rule:" content as progression_rule. Never place those labelled lines in
  coaching_cues. Ignore a bare separator label such as "Regression /" rather
  than rendering it as athlete guidance.
''',
        '''- When the plan states them, carry per-block detail into each block:
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
''',
    ),
    (
        '''                  "coaching_cues": ["..."], "regression_options": ["..."], "substitutions": ["..."], "progression_rule": "..."
''',
        '''                  "coaching_cues": ["..."], "regression_options": ["..."], "substitutions": ["..."],
                  "progression_rule": "...", "stop_rules": ["..."]
''',
    ),
]
for old, new in replace_rules:
    if generation.count(old) != 1:
        raise SystemExit(f"structured_plan_generation.py: prompt match count {generation.count(old)}")
    generation = generation.replace(old, new, 1)
generation_path.write_text(generation)

# Frontend pure helper: use new stop_rules and repair legacy mixed progression at display time.
structured_path = Path("web/lib/structured-plan.ts")
structured = structured_path.read_text()
insertion_marker = '// A stop rule reads like "Stop on sharp pain." / "Stop the set if punch speed\n'
helpers_ts = r'''const EMBEDDED_STOP_RULE_LABEL_RE = /\bstop(?:\s+rule)?\s*:\s*/i;
const PROGRAMMING_ONLY_PROGRESSION_RE =
  /^\s*(?:maintain(?:\s+(?:the|this))?\s+dose|keep\s+(?:the\s+)?dose\s+small|do\s+not\s+(?:add|increase)\s+(?:sets?|volume)|no\s+(?:set|volume)\s+increase)\b/i;
const NEGATED_PROGRESSION_RE =
  /\b(?:do\s+not|don't|never)\s+(?:add|increase|progress|advance|raise|build|extend)\b/i;
const POSITIVE_PROGRESSION_RE =
  /\b(?:progress|advance|increase|raise|build|extend|heavier|more\s+resistance|reduce\s+assistance)\b/i;
const TAPER_PROGRAMMING_RE = /\b(?:taper|fight[ -]?week|sharpness|freshness)\b/i;

function stripStopRuleLabel(value: string): string {
  return value.replace(/^\s*stop(?:\s+rule)?\s*:\s*/i, "").trim();
}

function isProgrammingOnlyProgression(text: string): boolean {
  if (NEGATED_PROGRESSION_RE.test(text)) {
    return PROGRAMMING_ONLY_PROGRESSION_RE.test(text) || TAPER_PROGRAMMING_RE.test(text);
  }
  if (POSITIVE_PROGRESSION_RE.test(text)) {
    return false;
  }
  return PROGRAMMING_ONLY_PROGRESSION_RE.test(text);
}

function dedupeStopRules(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const text = stripStopRuleLabel(value);
    const key = text.toLowerCase().replace(/[.\s]+$/, "");
    if (!text || seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(text);
  }
  return result;
}

export function getBlockAdjustmentDisplay(
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

'''
if insertion_marker not in structured:
    raise SystemExit("structured-plan.ts: stop helper insertion marker missing")
structured = structured.replace(insertion_marker, helpers_ts + insertion_marker, 1)
structured_path.write_text(structured)

# Renderer: render Progress and Stop rule as separate semantic rows.
renderer_path = Path("web/components/structured-plan-renderer.tsx")
renderer = renderer_path.read_text()
if renderer.count("  getBlockCoachingDisplay,\n") != 1:
    raise SystemExit("renderer: getBlockCoachingDisplay import mismatch")
renderer = renderer.replace(
    "  getBlockCoachingDisplay,\n",
    "  getBlockCoachingDisplay,\n  getBlockAdjustmentDisplay,\n",
    1,
)
if renderer.count("  progressionRuleLabel,\n") != 1:
    raise SystemExit("renderer: progressionRuleLabel import mismatch")
renderer = renderer.replace("  progressionRuleLabel,\n", "", 1)

old_renderer_logic = '''  const { cues, stopRules } = getBlockCoachingDisplay(block);
  const substitutions = getStringList(block.substitutions);
  const regressions = getStringList(block.regression_options);
  const progression = cleanText(block.progression_rule);
  const weekDirective = openBlockWeekDirective(openWeekIntent, block);
  // With a week directive on the card, the generic Progress aside is either the
  // same rule again (progression weeks) or a contradiction (deload week), so it
  // hides. A stop rule is safety wording and always stays.
  const showProgressionAside = Boolean(
    progression && (!weekDirective || progressionRuleLabel(progression) === "Stop rule"),
  );
  const adjustmentRules = [
    ...(showProgressionAside && progression ? [progression] : []),
    ...stopRules,
  ].filter(
    (rule, index, rules) =>
      rules.findIndex((candidate) => candidate.trim().toLowerCase() === rule.trim().toLowerCase()) ===
      index,
  );
'''
new_renderer_logic = '''  const { cues } = getBlockCoachingDisplay(block);
  const substitutions = getStringList(block.substitutions);
  const regressions = getStringList(block.regression_options);
  const { progression, stopRules } = getBlockAdjustmentDisplay(block);
  const weekDirective = openBlockWeekDirective(openWeekIntent, block);
  // A week directive owns progression/deload programming for open plans, while
  // block stop criteria are safety instructions and must always remain visible.
  const showProgressionAside = Boolean(progression && !weekDirective);
  const adjustmentRules = [
    ...(showProgressionAside && progression
      ? [{ label: "Progress" as const, text: progression }]
      : []),
    ...stopRules.map((text) => ({ label: "Stop rule" as const, text })),
  ];
'''
if renderer.count(old_renderer_logic) != 1:
    raise SystemExit(f"renderer: logic match count {renderer.count(old_renderer_logic)}")
renderer = renderer.replace(old_renderer_logic, new_renderer_logic, 1)

old_renderer_map = '''      {adjustmentRules.map((rule) => {
        const ruleLabel = progressionRuleLabel(rule);
        return (
          <p key={rule} className="sp-block-aside">
            <span className="sp-stat-label">{ruleLabel}</span>
            {/* "Stop rule" is glossed; "Progress" reads plainly on its own. */}
            <GlossaryTooltip term={ruleLabel} />
            {rule.replace(/^\s*stop(?:\s+rule)?\s*:\s*/i, "")}
          </p>
        );
      })}
'''
new_renderer_map = '''      {adjustmentRules.map((rule) => (
        <p key={`${rule.label}:${rule.text}`} className="sp-block-aside">
          <span className="sp-stat-label">{rule.label}</span>
          {/* "Stop rule" is glossed; "Progress" reads plainly on its own. */}
          <GlossaryTooltip term={rule.label} />
          {rule.text}
        </p>
      ))}
'''
if renderer.count(old_renderer_map) != 1:
    raise SystemExit(f"renderer: map match count {renderer.count(old_renderer_map)}")
renderer = renderer.replace(old_renderer_map, new_renderer_map, 1)
renderer_path.write_text(renderer)

# Focused backend regression tests.
Path("tests/test_structured_plan_stop_rules.py").write_text(r'''from api.structured_plan_generation import _normalize_block, build_structured_plan_prompt
from api.structured_plan_models import SessionBlock


def test_session_block_has_first_class_stop_rules():
    block = SessionBlock(
        block_id="band-punch",
        block_type="accessory",
        display_name="Band-Resisted Punch",
        stop_rules=["Sharp ankle pain or uncontrolled balance loss."],
    )
    assert block.stop_rules == ["Sharp ankle pain or uncontrolled balance loss."]


def test_normalizer_moves_stop_coaching_cue_out_of_cues():
    block = _normalize_block(
        {
            "block_id": "burst",
            "block_type": "conditioning",
            "display_name": "Explosive Boxing Burst Intervals",
            "coaching_cues": ["All-out punch intent", "Stop: if punch speed or stance control drops."],
        }
    )
    assert block["coaching_cues"] == ["All-out punch intent"]
    assert block["stop_rules"] == ["if punch speed or stance control drops."]
    assert "progression_rule" not in block


def test_normalizer_splits_valid_progression_from_embedded_stop_rule():
    block = _normalize_block(
        {
            "block_id": "band-punch",
            "block_type": "accessory",
            "display_name": "Band-Resisted Punch",
            "progression_rule": "Increase band resistance when punch speed stays high — Stop: sharp shoulder pain.",
        }
    )
    assert block["progression_rule"] == "Increase band resistance when punch speed stays high"
    assert block["stop_rules"] == ["sharp shoulder pain."]


def test_normalizer_hides_taper_programming_but_preserves_stop_rule():
    block = _normalize_block(
        {
            "block_id": "band-punch",
            "block_type": "accessory",
            "display_name": "Band-Resisted Punch",
            "progression_rule": "Maintain dose; do not add volume in taper window — Stop: any sharp ankle pain, new swelling, or loss of balance.",
        }
    )
    assert "progression_rule" not in block
    assert block["stop_rules"] == ["any sharp ankle pain, new swelling, or loss of balance."]


def test_converter_prompt_keeps_stop_rules_separate_from_progression():
    prompt = build_structured_plan_prompt(plan_markdown="D-7 — Band-Resisted Punch")
    assert '"stop_rules"' in prompt
    assert '"Stop rule:" content as stop_rules' in prompt
    assert '"Stop rule:" content as progression_rule' not in prompt
''')

# Focused pure frontend regression tests.
Path("web/lib/structured-plan-stop-rules.test.ts").write_text(r'''import test from "node:test";
import assert from "node:assert/strict";

import { getBlockAdjustmentDisplay } from "./structured-plan.ts";

test("pure exercise progression stays under Progress", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({ progression_rule: "Increase band resistance when speed stays high." }),
    { progression: "Increase band resistance when speed stays high.", stopRules: [] },
  );
});

test("legacy pure stop text becomes a stop rule instead of Progress", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({ progression_rule: "Stop if sharp quad pain appears." }),
    { progression: null, stopRules: ["Stop if sharp quad pain appears."] },
  );
});

test("legacy mixed progression splits into Progress and Stop rule", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({
      progression_rule: "Increase band resistance when speed stays high — Stop: sharp shoulder pain.",
    }),
    {
      progression: "Increase band resistance when speed stays high",
      stopRules: ["sharp shoulder pain."],
    },
  );
});

test("taper programming is not shown as exercise progression", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({
      progression_rule:
        "Maintain dose; do not add volume in taper window — Stop: any sharp ankle pain or uncontrolled balance loss.",
    }),
    {
      progression: null,
      stopRules: ["any sharp ankle pain or uncontrolled balance loss."],
    },
  );
});

test("explicit and legacy stop rules are preserved and deduplicated", () => {
  assert.deepEqual(
    getBlockAdjustmentDisplay({
      stop_rules: ["Stop: sharp ankle pain."],
      coaching_cues: ["Fast hands", "Stop: sharp ankle pain."],
    }),
    { progression: null, stopRules: ["sharp ankle pain."] },
  );
});
''')

# Renderer regression reproduces the Band-Resisted Punch screenshot failure.
Path("web/components/structured-plan-stop-rules.test.tsx").write_text(r'''import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { BlockCard } from "./structured-plan-renderer";

test("Band-Resisted Punch does not label taper safety text as Progress", () => {
  const html = renderToStaticMarkup(
    <BlockCard
      block={{
        block_id: "band-punch",
        block_type: "accessory",
        display_name: "Band-Resisted Punch",
        progression_rule:
          "Maintain dose; do not add volume in taper window — Stop: any sharp ankle pain, new swelling, or loss of balance.",
      }}
    />,
  );

  assert.equal(html.includes(">Progress</span>"), false);
  assert.equal(html.includes(">Stop rule</span>"), true);
  assert.equal(html.includes("any sharp ankle pain, new swelling, or loss of balance."), true);
});

test("a genuine progression and stop rule render as separate rows", () => {
  const html = renderToStaticMarkup(
    <BlockCard
      block={{
        block_id: "band-punch",
        block_type: "accessory",
        display_name: "Band-Resisted Punch",
        progression_rule: "Increase band resistance when punch speed stays high.",
        stop_rules: ["Sharp shoulder pain or a clear drop in punch mechanics."],
      }}
    />,
  );

  assert.equal(html.includes(">Progress</span>"), true);
  assert.equal(html.includes("Increase band resistance when punch speed stays high."), true);
  assert.equal(html.includes(">Stop rule</span>"), true);
  assert.equal(html.includes("Sharp shoulder pain or a clear drop in punch mechanics."), true);
});
''')
