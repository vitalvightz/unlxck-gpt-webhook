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

- Style match (exact): `+1.5`
- Phase match: `+1.0`
- Energy system match: `+0.75`
- Equipment match: `+0.5`
- Weakness tag match: `+0.6` each (max one)
- Goal tag match: `+0.5` each (max one)
- Fatigue penalty: `-1.0` (high) or `-0.5` (moderate) if the drill has `high_cns`
- Random noise: `±0.2`

Energy system emphasis per phase is set by `PHASE_SYSTEM_RATIOS` and the ratio of style‑specific to general drills uses `STYLE_CONDITIONING_RATIO`.

#### Style Matching in Conditioning

Two banks feed the conditioning generator:

1. `conditioning_bank.json` – general drills for any athlete.
2. `style_conditioning_bank.json` – drills written for specific fighting styles.

`STYLE_CONDITIONING_RATIO` sets how many style drills appear in each phase:

```
GPP   → 20% style drills
SPP   → 60% style drills
TAPER → 5%  style drills
```

In the **general bank**, style tags simply add `+1.0` each to a drill’s score. A drill can still be chosen without them because ranking, not filtering, determines selection.

In the **style bank**, every drill already matches a tactical style. Tag overlap is used only to rank which style drills are pulled first.

The style-match score never changes the bank ratio above—it just sorts the options within each bank.

**Phase calculation** (`camp_phases.py`)

Phase weeks come from `BASE_PHASE_RATIOS` with style adjustments. Professional athletes shift 5% from GPP to SPP. Ratios are rebalanced so the weeks always sum to the camp length and taper is capped at two weeks. When multiple styles move the same phase in one direction, the combined adjustment is capped at **7%** to keep camps balanced.

### Style-Specific Phase Rules

Certain tactical styles impose hard minimums or maximums on the camp phases. These rules come from `STYLE_RULES` in `camp_phases.py` and are enforced both when the ratios are first calculated and again after the weeks are rounded:

- **Pressure fighter**
  - `SPP_MIN_PERCENT: 0.45` – at least 45% of the schedule must be SPP. Weeks are pulled from GPP if needed.
  - `MAX_TAPER: 0.10` – taper can be no more than 10% of the camp. Excess taper weeks go back into SPP.
- **Clinch fighter**
  - `TAPER_MAX_DAYS: 9` – taper tops out at nine days (roughly 1–1.5 weeks). Extra days shift to SPP.
  - `SPP_CLINCH_RATIO: 0.40` – requires at least 40% of the camp in SPP.
- **Grappler**
  - `GPP_MIN_PERCENT: 0.35` – guarantees at least 35% of the camp in GPP. SPP is reduced if necessary.

These constraints ensure fighters with those styles emphasize the most relevant phases even after other adjustments.

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
