# UNLXCK Fight Camp Builder

This repository generates fight camp programs by combining local training modules. The main script reads athlete data, assembles strength, conditioning, recovery and other blocks, then exports the result directly to Google Docs.

Recent updates removed the OpenAI dependency and now build plans entirely from the module outputs. Short-camp handling and style-specific rules still adjust the phase weeks correctly via the helper `_apply_style_rules()`.

### Professional Status

Setting the **Professional Status** field to `pro` or `professional` adjusts the camp ratios when the camp is four weeks or longer. The shift from GPP to SPP depends on fatigue, weight cutting and mindset:

- **Clean athlete** – low fatigue, no weight cut and an approved mindset block ("confidence" or "generic"): **+10%** SPP
- **Reliable athlete** – low/moderate fatigue, cutting ≤5% bodyweight and no burnout/overthinking blocks: **+7.5%** SPP
- **Normal pro** – all other cases: **+5%** SPP

GPP is reduced by the same amount but never drops below 15% of the total camp.
The valid mindset blocks for the clean-pro check are listed in
`APPROVED_TIER3_BLOCKS` inside `camp_phases.py`.

#### Approved mental blocks for Tier 3 (+10% SPP)

Only `confidence` and `generic` keep intensity, resilience and volume high enough
to qualify a professional athlete for the full bonus.

### Module Weightings & Scoring

The generator ranks drills and exercises based on a simple heuristic score. Each module applies its own weights:

**Strength module** (`strength.py`)

- Weakness tags: `+1.5` each
- Goal tags: `+1.25` each
- Style tags: `+1.0` each, plus an extra `+2` when two style tags match
- Additional `+1` when three or more total tags match
- Phase tag boosts (e.g. triphasic or contrast) add `+1` or more per tag
- Fatigue penalties: `-1.5` (high) or `-0.75` (moderate) for heavy equipment or compound lifts
- Missing equipment removes the exercise (`-999`)
- Rehab exercises carry a phase penalty (`-1` GPP, `-3` SPP, `-2` TAPER)

**Conditioning module** (`conditioning.py`)

- Weakness tags: `+2.5` each (max two)
- Goal tags: `+2.0` each (max two)
- Style tags: `+1.0` each (max two)
- Fight-format tags: `+1.0` (max one)
- Energy system weight from `format_energy_weights.json` multiplies the base score
- High CNS drills are penalized `-2.0` (high fatigue) or `-1.0` (moderate fatigue)
- Style‑specific drills score `+3.0` for style, `+1.5` for phase, `+1.0` for matching energy system and `+1.0` for accessible equipment

Energy system emphasis per phase is set by `PHASE_SYSTEM_RATIOS` and the ratio of style‑specific to general drills uses `STYLE_CONDITIONING_RATIO`.

**Phase calculation** (`camp_phases.py`)

Phase weeks come from `BASE_PHASE_RATIOS` with style adjustments. When the camp is at least four weeks and the athlete is pro, GPP time shifts to SPP based on fatigue, weight cut and mindset, never letting GPP fall below 15%. Ratios are rebalanced so the weeks always sum to the camp length and taper is capped at two weeks.

**Mindset module** (`mindset_module.py`)

Keyword counts determine the top mental blocks. The two highest scoring blocks feed into the phase mindset cues.

**Training context** (`training_context.py`)

The helper `allocate_sessions()` assigns weekly sessions based on available days:

```
≤3 days  → {'strength': 1, 'conditioning': 1, 'recovery': 1}
4 days   → {'strength': 2, 'conditioning': 1, 'recovery': 1}
5 days   → {'strength': 2, 'conditioning': 2, 'recovery': 1}
>5 days  → {'strength': 3, 'conditioning': 2, 'recovery': 1}
```
