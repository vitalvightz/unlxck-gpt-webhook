# Training Guide for Teens

This guide explains every tag used in the fight camp builder, how scoring works and how your weekly sessions are chosen. It is written so a 17 year old can easily follow along.

## Tag Dictionary

Tags are short labels that describe each exercise. The program matches them to your goals, weaknesses and fighting style to pick the best drills. Here's what they mean in simple terms:

- **ATP-PCr** – trains quick bursts of power
- **acceleration** – helps you speed up rapidly
- **adductors** – works the inner thighs
- **aerobic** – builds long‑lasting endurance
- **agility** – improves quick direction changes
- **anaerobic_alactic** – boosts short, intense efforts
- **anti_rotation** – resists twisting forces
- **arm_dominant** – mainly uses the arms
- **athletic** – general athleticism
- **balance** – challenges balance and stability
- **bjj** – grappling focused
- **boxing** – boxing focused
- **clinch** – trains clinch skills
- **cns_freshness** – keeps your nervous system fresh
- **cognitive** – adds decision making or reaction work
- **compound** – multi‑joint strength moves
- **conditioning** – improves overall conditioning
- **contrast_pairing** – pairs heavy and explosive work
- **coordination** – improves body control
- **core** – targets the core muscles
- **deadlift** – deadlift variations
- **eccentric** – emphasizes lowering the weight
- **elastic** – uses elastic or band resistance
- **endurance** – boosts endurance in general
- **environmental** – needs special environments
- **explosive** – builds explosive power
- **footwork** – trains footwork
- **glycolytic** – pushes hard efforts that burn
- **grip** – strengthens grip
- **hamstring** – focuses on hamstrings
- **hip_dominant** – works the back side of the hips and legs
- **horizontal_power** – power in horizontal direction
- **improvised** – can use makeshift equipment
- **intensity** – internal tag for difficulty
- **jump_rope** – jump rope work
- **kettlebell** – uses kettlebells
- **lateral_power** – power side to side
- **low_cns** – light on the nervous system
- **low_impact** – gentle on the joints
- **low_volume** – small amount of reps
- **lunge_pattern** – lunge movements
- **mental_toughness** – tests mental grit
- **mma** – mixed martial arts drills
- **mobility** – improves range of motion
- **muay_thai** – muay thai focused
- **overhead** – pressing overhead
- **parasympathetic** – promotes relaxation
- **phases** – internal phase tag
- **plyometric** – jump or rebound exercises
- **posterior_chain** – strengthens the back side
- **pull** – pulling movements
- **quad_dominant** – works the front of the legs
- **rate_of_force** – how fast you create force
- **reactive** – quick reaction training
- **recovery** – helps you recover
- **rehab_friendly** – gentle enough for rehab
- **rotational** – adds twisting power
- **sharpness** – sharp technical drills
- **shoulders** – shoulder strength
- **skill** – pure skill work
- **sled** – sled pushes or pulls
- **speed** – pure speed drills
- **striking** – striking oriented
- **system** – internal system tag
- **tags** – internal tag list
- **top_control** – ground control skills
- **transition** – movement transitions
- **triphasic** – eccentric, isometric and concentric phases
- **triple_extension** – hips, knees and ankles extend together
- **unilateral** – one side at a time
- **upper_body** – upper‑body work
- **visual_processing** – trains your eyes
- **work_capacity** – improves work capacity
- **wrestling** – wrestling focused
- **zero_impact** – no impact on the joints

## Scoring Weights

When the program chooses drills, it scores each one based on matching tags.

### Strength Module
- Weakness tag: **+0.6** each
- Goal tag: **+0.5** each
- Style tag: **+0.3** each
- Two style tags together: **+0.2** bonus
- Three or more style tags: **+0.1** bonus
- Three total matches of any kind: **+0.2** bonus
- Phase tag (GPP/SPP/TAPER): **+0.4** each
- Moderate fatigue: **-0.35** penalty
- High fatigue: **-0.75** penalty
- Missing equipment: exercise skipped
- Rehab exercises: **-0.5** in GPP, **-1.0** in SPP, **-0.75** in TAPER

### Conditioning Module
- Weakness tag: **+2.5** each (max two)
- Goal tag: **+2.0** each (max two)
- Style tag: **+1.0** each (max two)
- Fight format tag: **+1.0** (max one)
- Energy system multiplier from `format_energy_weights.json`
- High CNS drills: **-1.0** or **-2.0** penalty if fatigued
- Style‑specific drills: **+3.0** for style, **+1.5** for phase, **+1.0** for matching energy system and **+1.0** for available equipment

### Mindset and Phases
- Your top two mindset keywords become focus cues
- Phase weeks are based on `BASE_PHASE_RATIOS` with style tweaks
- Pros shift about **5%** from GPP to SPP and taper never exceeds two weeks

## Weekly Session Allocation

`allocate_sessions()` in `training_context.py` splits your chosen training **frequency** into the number of strength, conditioning and recovery sessions:

```
≤3 days  → {'strength': 1, 'conditioning': 1, 'recovery': 1}
4 days   → {'strength': 2, 'conditioning': 1, 'recovery': 1}
5 days   → {'strength': 2, 'conditioning': 2, 'recovery': 1}
>5 days  → {'strength': 3, 'conditioning': 2, 'recovery': 1}
```

Available training days simply tell the program which slots can be filled.

## Format Templates

`format_round_templates.json` defines round and rest times for each sport. `format_energy_weights.json` says how important each energy system is for those formats.

## Base Phase Ratios

`BASE_PHASE_RATIOS` in `camp_phases.py` show how much of a camp is spent in GPP, SPP and TAPER for camps of one to sixteen weeks. Styles tweak these numbers, and pros move about five percent of GPP over to SPP when the camp is four weeks or longer.

## Style Conditioning Bank

`style_conditioning_bank.json` adds conditioning drills tailored to tactical styles. Around 20% of your conditioning in GPP, 60% in SPP and 5% in TAPER comes from this bank. Drills get **+3.0** for matching your style, **+1.5** if designed for the current phase, **+1.0** for hitting the right energy system and **+1.0** if you have the required gear.

## Tactical Style Scoring

Normal conditioning drills give **+1.0** for each matching style tag (up to two). Drills from the style bank score the larger bonuses above, so matching your style heavily influences which exercises are picked.

## Putting It All Together

1. Choose your weekly training frequency.
2. `allocate_sessions()` splits it into strength, conditioning and recovery days.
3. Exercises are scored using the weights above and sorted by score.
4. Style-specific drills enter the mix based on the current phase.
5. The highest-scoring exercises fill your schedule until all sessions are assigned.
