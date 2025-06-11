# Tag and Scoring Cheat Sheet

This document is a quick reference for the tags used throughout the fight camp builder and how the program scores and selects exercises. It is written in plain language so that even a teenager can follow along.

## What Are Tags?

Tags are short keywords attached to every drill or exercise. They describe what the movement trains (for example `core` or `explosive`) or who it suits (like `wrestling` or `muay_thai`). When the program builds your plan it looks at your goals, weaknesses and fighting style and then picks moves with the best matching tags.

Below is a list of all tags found in the banks. The descriptions are brief so you have a general idea of what each tag means.

- **ATP-PCr** – general tag for ATP-PCr.
- **acceleration** – general tag for acceleration.
- **adductors** – general tag for adductors.
- **aerobic** – develops endurance.
- **agility** – boosts agility.
- **anaerobic_alactic** – develops endurance.
- **anti_rotation** – general tag for anti rotation.
- **arm_dominant** – general tag for arm dominant.
- **athletic** – general tag for athletic.
- **balance** – challenges balance.
- **bjj** – grappling related.
- **boxing** – striking specific.
- **clinch** – general tag for clinch.
- **cns_freshness** – general tag for cns freshness.
- **cognitive** – adds decision making or brain work.
- **compound** – general tag for compound.
- **conditioning** – improves conditioning.
- **contrast_pairing** – general tag for contrast pairing.
- **coordination** – general tag for coordination.
- **core** – targets the core.
- **deadlift** – general tag for deadlift.
- **eccentric** – general tag for eccentric.
- **elastic** – general tag for elastic.
- **endurance** – develops endurance.
- **environmental** – general tag for environmental.
- **explosive** – general tag for explosive.
- **footwork** – general tag for footwork.
- **glycolytic** – trains high intensity energy systems.
- **grip** – strengthens grip.
- **hamstring** – general tag for hamstring.
- **hip_dominant** – targets posterior chain.
- **horizontal_power** – builds power or explosiveness.
- **improvised** – general tag for improvised.
- **intensity** – internal use label.
- **jump_rope** – general tag for jump rope.
- **kettlebell** – general tag for kettlebell.
- **lateral_power** – builds power or explosiveness.
- **low_cns** – general tag for low cns.
- **low_impact** – general tag for low impact.
- **low_volume** – general tag for low volume.
- **lunge_pattern** – general tag for lunge pattern.
- **mental_toughness** – general tag for mental toughness.
- **mma** – grappling related.
- **mobility** – improves joint mobility.
- **muay_thai** – striking specific.
- **overhead** – general tag for overhead.
- **parasympathetic** – promotes recovery and relaxation.
- **phases** – internal use label.
- **plyometric** – uses plyometric movements.
- **posterior_chain** – targets posterior chain.
- **pull** – general tag for pull.
- **quad_dominant** – focuses on quads.
- **rate_of_force** – general tag for rate of force.
- **reactive** – improves reaction speed.
- **recovery** – helps recovery.
- **rehab_friendly** – general tag for rehab friendly.
- **rotational** – general tag for rotational.
- **sharpness** – general tag for sharpness.
- **shoulders** – general tag for shoulders.
- **skill** – general tag for skill.
- **sled** – general tag for sled.
- **speed** – general tag for speed.
- **striking** – striking specific.
- **system** – internal use label.
- **tags** – internal use label.
- **top_control** – general tag for top control.
- **transition** – general tag for transition.
- **triphasic** – general tag for triphasic.
- **triple_extension** – general tag for triple extension.
- **unilateral** – works one side at a time.
- **upper_body** – upper body work.
- **visual_processing** – trains eyes and coordination.
- **work_capacity** – general tag for work capacity.
- **wrestling** – grappling related.
- **zero_impact** – general tag for zero impact.

## Scoring Basics

Every module looks at how many of its tags match your goals, weaknesses and fighting style. More matches mean a higher score. Exercises with the best scores get picked first. Here is a simplified look at the weighting system from the code:

### Strength Module
- Weakness tag match: **+0.6** each
- Goal tag match: **+0.5** each
- Style tag match: **+0.3** each
- Two style tags together: **+0.2** bonus
- Three or more style tags: **+0.1** bonus
- Three total matches (goals, weaknesses or style): **+0.2** bonus
- Phase tag match (GPP/SPP/TAPER): **+0.4** each
- Fatigue penalty: **-0.35** (moderate) or **-0.75** (high)
- Missing required equipment: exercise is skipped
- Rehab exercise penalty: **-0.5** in GPP, **-1.0** in SPP, **-0.75** in TAPER

### Conditioning Module
- Weakness tag match: **+2.5** each (max two)
- Goal tag match: **+2.0** each (max two)
- Style tag match: **+1.0** each (max two)
- Fight format tag: **+1.0** (max one)
- Energy system multiplier from `format_energy_weights.json`
- High CNS drills: **-1.0** or **-2.0** penalty if you're fatigued
- Style‑specific drills: **+3.0** for style, **+1.5** for phase, **+1.0** for matching energy system and **+1.0** if you have the right equipment

### Mindset and Phase Calculation
- Mindset keywords are counted and the top two become your focus cues
- Phase weeks come from `BASE_PHASE_RATIOS` with style tweaks. Pros shift **5%** from GPP to SPP and taper never lasts more than two weeks

## How Sessions Are Scheduled

The helper `allocate_sessions()` in `training_context.py` decides how many strength, conditioning and recovery days you get each week. It only cares about your chosen **training frequency**:

```
≤3 days  → {'strength': 1, 'conditioning': 1, 'recovery': 1}
4 days   → {'strength': 2, 'conditioning': 1, 'recovery': 1}
5 days   → {'strength': 2, 'conditioning': 2, 'recovery': 1}
>5 days  → {'strength': 3, 'conditioning': 2, 'recovery': 1}
```

The days you actually have available just tell the program which slots to fill. If you list seven free days but pick a frequency of five, you'll only get five sessions.


## Format Templates
The file `notes/format_round_templates.json` sets default round and rest times for each sport. Boxing rounds are 3 minutes with a minute break, while MMA rounds last 5 minutes. These templates help the workouts follow the same rhythm as a real match.

## Base Phase Ratios
`BASE_PHASE_RATIOS` in `camp_phases.py` shows how much of a fight camp belongs to GPP (general prep), SPP (sport prep) and TAPER. An 8‑week camp starts around **40%** GPP, **45%** SPP and **15%** taper before style tweaks or pro bonuses.

## Style Conditioning Bank
`style_conditioning_bank.json` collects drills written for specific fighting styles like brawler or counter striker. The program mixes them in using `STYLE_CONDITIONING_RATIO` so more style drills appear in SPP than in GPP or TAPER.

**How style drills score**
- **+3.0** if the tags match your tactical style
- **+1.5** if they fit the current phase
- **+1.0** when the energy system lines up
- **+1.0** if you own the right equipment
- **+0.5** bonus just for variety

The higher the score, the more likely that drill shows up in your plan.
