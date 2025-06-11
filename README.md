# UNLXCK Fight Camp Builder

This repository generates fight camp programs by combining local training modules. The main script reads athlete data, assembles strength, conditioning, recovery and other blocks, then exports the result directly to Google Docs.

### Repository Structure

```
data/      → JSON banks and other static assets
fightcamp/ → Python package with all modules and API entrypoint
notes/     → Reference JSON and tag documentation
```

Run the application with `python -m fightcamp.main` from the project root.

Recent updates removed the OpenAI dependency and now build plans entirely from the module outputs. Short-camp handling and style-specific rules still adjust the phase weeks correctly via the helper `_apply_style_rules()`.

### Professional Status

Setting the **Professional Status** field to `pro` or `professional` adjusts the camp ratios when the camp is four weeks or longer. The shift from GPP to SPP depends on fatigue, weight cutting and mindset:

- **Elite Tier 3** – low fatigue, no weight cut and mindset blocks only `generic` or `confidence`: **+10%** SPP
- **Tier 2** – low/moderate fatigue, cutting ≤5% bodyweight and no `motivation`, `gas tank` or `injury fear` blocks: **+7.5%** SPP
- **Tier 1** – all other pros: **+5%** SPP

GPP is reduced by the same amount but never drops below 15% of the total camp.

### Module Weightings & Scoring

The generator ranks drills and exercises based on a simple heuristic score. Each module applies its own weights:

**Strength module** (`strength.py`)

- Weakness tags: `+0.6` each
- Goal tags: `+0.5` each
- Style tags: `+0.3` each with a small synergy bonus (`+0.2` for two matches, `+0.1` for three or more)
- When three or more total tags match, add `+0.2`
- Phase tag matches add `+0.4` each
- Fatigue penalties: `-0.75` (high) or `-0.35` (moderate)
- Missing required equipment removes the exercise (`-999`)
- Rehab exercises incur `-0.5` in GPP, `-1.0` in SPP and `-0.75` in TAPER

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

Phase weeks come from `BASE_PHASE_RATIOS` with style adjustments. Professional athletes shift 5% from GPP to SPP. Ratios are rebalanced so the weeks always sum to the camp length and taper is capped at two weeks.

**Mindset module** (`mindset_module.py`)

Keyword counts determine the top mental blocks. The two highest scoring blocks feed into the phase mindset cues.

**Training context** (`training_context.py`)

The helper `allocate_sessions()` now takes a phase and returns the split for
strength, conditioning and recovery. The schedule adapts across phases:

```
1 session/week
  GPP   → 1 Strength
  SPP   → 1 Conditioning
  Taper → 1 Conditioning

2 sessions/week
  GPP   → 1 Strength, 1 Conditioning
  SPP   → 1 Strength, 1 Conditioning
  Taper → 1 Conditioning, 1 Recovery

3 sessions/week
  GPP   → 1 Strength, 1 Conditioning, 1 Recovery
  SPP   → 1 Strength, 2 Conditioning
  Taper → 1 Strength, 1 Conditioning, 1 Recovery

4 sessions/week
  GPP   → 2 Strength, 1 Conditioning, 1 Recovery
  SPP   → 1 Strength, 2 Conditioning, 1 Recovery
  Taper → 1 Strength, 1 Conditioning, 2 Recovery

5 sessions/week
  GPP   → 2 Strength, 2 Conditioning, 1 Recovery
  SPP   → 2 Strength, 2 Conditioning, 1 Recovery
  Taper → 1 Strength, 1 Conditioning, 3 Recovery

6 sessions/week
  GPP   → 2 Strength, 3 Conditioning, 1 Recovery
  SPP   → 2 Strength, 3 Conditioning, 1 Recovery
  Taper → 1 Strength, 1 Conditioning, 4 Recovery
```

`Weekly Training Frequency` is the number of sessions the athlete plans to
complete each week. The `Time Availability for Training` field simply lists
which days are open. Frequency does **not** automatically equal the count of
available days—a fighter might have seven days free but only train five times
per week. The program schedules sessions based on the provided frequency and
assigns them to the supplied training days.

The function `calculate_exercise_numbers()` expands on this by converting the
weekly session split into actual exercise counts.  Strength days output `7`,
`6` or `4` exercises per session in `GPP`, `SPP` and `TAPER` respectively while
conditioning days use `4`, `3` and `2`.  Recovery is implied by days without
strength or conditioning work.
