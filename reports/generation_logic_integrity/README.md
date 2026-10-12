# UNLXCK generation logic integrity audit

Read-only audit of the full plan-generation chain (intake → athlete model →
constraints → selection → composition → weekly scheduling → countdown morph →
goal preservation → Stage 2 handoff → validation/release → structured cards).
Baseline: `Main` at `0926f2e` (after #2857). No generator code, exercise data,
prompt, safety policy, schema or production record was changed; the only files
added are this report and its read-only reproduction scripts.

| File | Contents |
| --- | --- |
| `README.md` | Executive summary, method, pipeline and ownership map |
| `findings.md` | Evidence-backed register: confirmed defects, probable risks, deliberate policy verified |
| `known_case.md` | The 21-day boxer reproduction and the seven-hop trace of the missing trunk work |
| `scenario_matrix.md` | 32 deterministic scenarios across sports, modes, phases, injuries, cuts and frequencies |
| `roadmap.md` | Six focused PRs that repair the shared root causes, with regression tests |
| `verification.md` | Tests run, coverage gaps, limitations |
| `repro/` | Harness and probes (Stage 1 only, frozen clock, fixed seed, no model calls) |
| `evidence/` | Raw matrix output and summary table |

## Executive summary

**The known case is reproduced and fully explained.** A 0-0 amateur boxer,
21 days out, primary weakness *core/trunk strength*, receives no trunk work in
either injury variant. The loss is not one bug: seven independently
"reasonable" hops close every path (`known_case.md`). The two that originate
it are (1) the strength selector never expands the weakness into the tags the
bank uses — no exercise is tagged `trunk_strength` — and (2) goal preservation
*delegates* trunk strength to a composition subsystem that has no candidates,
no reserved capacity under a readiness cap, and no verifier. The deliberate
D-17 behaviour is intact and is not implicated.

**The same structure repeats across the system.** 15 confirmed findings
reduce to six root causes:

| RC | Root cause | Worst consequence | Findings |
| --- | --- | --- | --- |
| A | Weaknesses "delegated" with no owner that guarantees or verifies delivery; weakness tokens never expanded for strength | Selected limiter silently produces nothing; a `strength` selection is erased at ≤ 20 days | F01, F02, F03, F12 |
| B | Roles are created without asking whether a legal, eligible member exists that day | Titled sessions with zero content ship (12 of 27 completed scenarios, including the known case's D-15 conditioning day) | F08, F14 |
| C | Goal preservation's microdose tier invents exercises and appends them to closed sessions after every safety owner has run | **P0:** sprint starts on injured feet/ankles/knees; loaded carries for bodyweight-only and shoulder-injured athletes; carries certify "build strength" | F06, F07 |
| D | Strength membership is composed before the governor; three calendar movers use three destination doctrines | Two strength sessions on one day; strength stacked on glycolytic days; stale membership | F09 |
| E | Two definitions of one fact ("loaded", "low-load trunk", coverage window) in different owners | Valid plans hit a deterministic hold (no structured card); heavy sled pushes embedded as "low-load trunk" and hidden from the load calendar | F04, F10, F13 |
| F | Bank/library coverage gaps | **P0:** foot injuries never exclude jumps/landings; long wrestling and Muay Thai camps crash | F05, F11, F02 |

**What already works** (verified, see `findings.md`): the D-14/D-17
hard-sparring resolver, injury triage gates, late-tail ownership, fight-day
protocol, determinism (seed- and run-stable), and the release invariant. All
1,312 focused planner/validator tests pass (full fast lane: 14,597 passed, 4
unrelated environment/isolation failures) — which is itself a finding: the suites test
each owner with hand-built inputs and never assert end-to-end that a selected
goal or weakness is delivered, that a scheduled role has members, or that a
downstream author respects injury and equipment (`verification.md`).

**Recommended repair:** six PRs, in order — safety bypasses (P0); crash and
silent goal loss; role existence gated on fill-ability; one calendar order and
one "loaded" definition; weakness delivery (tag expansion, trunk metadata,
reserved embedded slot, delegated-coverage verdict); honest goal evidence and
contract sync (`roadmap.md`). Each lives in an existing canonical owner and
none adds a parallel rule.

## Method

1. Read `PLANNER_ARCHITECTURE_CONTRACT.md`, `STAGE2_PAYLOAD_SPEC.md`,
   `docs/goal_preservation.md`, `docs/hard_sparring_cutoff.md`,
   `docs/pre-hard-spar-strength-implementation.md` and the metadata-integrity
   report (used as the taxonomy baseline, not repeated).
2. Built a deterministic harness over the real entry point
   (`fightcamp.main.generate_plan_sync`): frozen clock, fixed seed, synthetic
   anonymised athletes, guided-injury payloads in the web form's shape.
3. Ran the known case, a 32-scenario pairwise matrix and targeted probes;
   instrumented internal functions with wrappers/profilers (no source edits)
   to see candidate pools, caps, classifier verdicts and bonus decisions.
4. Checked each output against the owning module's own contract and the
   planning brief's own claims; every finding cites the file/function and a
   reproducing scenario.
5. Ran the existing planner/validator suites (`verification.md`).

No Stage 2 model call was made: every finding exists in the deterministic
handoff Stage 2 is instructed not to change.

## Pipeline and ownership map

Actual execution order of a dated normal camp (`fightcamp/main.py` →
`plan_pipeline_*` → `stage2_payload._build_planning_brief`), with the
canonical owner of each decision and where this audit found that a downstream
layer re-decides it.

```text
Intake  input_parsing.PlanInput.from_payload ........ owner: input_parsing
   └─ strips "strength" goal/weakness at <=20d + hard day        [F12 silent loss]
Triage  injury_triage ............................... owner: injury_triage   ✓
Runtime/athlete model  plan_pipeline_runtime ........ owner: runtime model
Stage 1 selection  plan_pipeline_blocks
   ├─ strength.generate_strength_block .............. owner: Stage 1 selection
   │    weakness tokens not expanded                              [F01]
   │    late-window gate × bank metadata                          [F02, F05 data]
   ├─ conditioning.generate_conditioning_block ...... owner: Stage 1 selection
   │    missing_systems recorded, never consumed by the role map  [F08]
   └─ rehab / support blocks
Planning brief  stage2_payload.build_planning_brief
   ├─ priority profile / limiter ..................... owner: planning brief  ✓
   ├─ stage2_role_map._build_weekly_role_map ......... owner: role budget + placement
   │    creates system roles without fill-ability check            [F08]
   ├─ sparring_dose_planner .......................... owner: contact load    ✓ (D-14/D-17)
   ├─ fill_missing_session_days, camp_week_fillers ... owner: placement completion / support inserts
   │    Tactical Watch bank exhaustion raises                      [F11]
   ├─ session_composition.compose_normal_strength_assignments   (BEFORE governor) [F09]
   │    adjacent-recovery path relocates via calendar mover       [F09]
   │    trunk reserve unreachable under cap                       [F03]
   ├─ late_camp_role_morph → calendar_integrity governor → pre-hard cap
   │    governor stacks onto occupied ALLOW days                  [F09]
   ├─ session_composition.compose_normal_conditioning_assignments
   │    empty roles survive; low-load trunk classifier too broad  [F08, F04]
   ├─ late-tail assignment builder (D-13 inward) ..... owner: late-fight path ✓ (style-taper primer preference = policy)
   ├─ prescription_resolver ......................... owner: effective dose
   │    also drops members (pre-hard pruning)                     [R6]
   │    "loaded" ≠ authority gate's "loaded"                       [F10]
   ├─ standalone minimum, realised-load revalidation
   │    skips embedded support cost                               [F04]
   ├─ labels
   └─ goal_preservation.reconcile_goal_preservation .. owner: goal coverage
        delegated weaknesses: no verdict                          [F03]
        microdose tier invents members after every safety owner  [F06, F07]
        coverage window / proximity deferral off the calendar     [F13]
Handoff  finalizer packet + locked render manifest ... owner: finalizer boundary
   empty closed roles emitted as zero-exercise sessions          [F08]
Stage 2 AI .......................................... wording only ✓ (not run)
Validation / release  stage2_validator + planner_authority_integrity
   loaded-by-equipment blocker → hold → no structured card       [F10]
   no check for empty normal-camp closed roles                   [F08]
Persistence  _release_held_plan_with_flags ............ releases holds with flags ✓ (by design)
Structured card  api/structured_plan_generation ...... faithful to Stage 2 text (R3)
```

Ownership violations against the contract: composition relocates roles and
runs before the governor (contract §2, §4); goal preservation adds exercises
and doses to closed roles (§3, invariant 11); the dose owner drops members
(not listed as a membership writer). Duplicated authorities: "loaded"
(resolver vs authority gate), D-day resolution
(`session_composition._role_days_until_fight` vs `calendar_context.role_d_day`),
destination doctrine (governor vs adjacent-recovery vs realised-load
revalidation).

## Reproducing

```bash
pip install -r requirements-dev-fast.txt   # spaCy optional
cd reports/generation_logic_integrity/repro
python matrix.py                      # all scenarios -> out/
python matrix.py S01_boxer21_noinj    # one scenario
python trace_trunk.py                 # composition caps and trunk records (known case)
python trace_bonus.py                 # core-balance bonus decisions per phase
python injury_matrix.py               # foot/ankle/knee/Achilles probes
python crash_probe.py                 # TacticalWatchBankExhausted grid
python strength_drop_probe.py         # 20 vs 21 day strength-goal erasure
python deleg_probe.py                 # delegated weakness delivery
python experiment_expand.py           # diagnostic: weakness tag expansion (monkeypatched, not a fix)
```

The scripts import the generator read-only and monkeypatch only for
observation (`experiment_expand.py` is the one counterfactual and is labelled
as such). `out/` and JSON outputs are git-ignored.
