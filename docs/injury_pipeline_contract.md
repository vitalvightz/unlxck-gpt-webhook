# Injury Pipeline Contract

## Purpose
This document defines the current injury data flow and ownership across the planning pipeline.

## Contract Summary
The injury pipeline is ordered and deterministic. Structured injury data is the source of truth when available.

**Priority rule:**
1. Structured/guided injury data (including the `parsed_injuries` artifact) must outrank raw injury text.
2. Raw injury reparsing is fallback-only behavior.

---

## 1) Frontend guided injury capture
The frontend captures guided injury details in structured form (for example: area, type, severity, symptoms, timeline).

This stage exists to collect explicit injury signals before free-text interpretation.

## 2) `input_parsing.py` builds injury artifacts
`input_parsing.py` is responsible for producing the core injury-related fields:
- `injuries`
- `guided_injury`
- `parsed_injuries`
- `restrictions`

These artifacts are the canonical parsed outputs used downstream.

`restrictions` are parser-owned truth at this stage and are later mapped to `injury_restrictions` in downstream transport/model layers.

## 3) `injury_triage.py` decides safety mode
`injury_triage.py` evaluates injury context and sets the plan safety mode. Supported outcomes:
- `full_plan`
- `needs_review`
- `restricted_rehab_only`
- `medical_hold`

This triage decision governs whether normal planning proceeds or is constrained/blocked.

## 4) `TrainingContext` carries injury fields forward
`TrainingContext` transports injury-related fields from parsing/triage into later planner stages without reinterpreting their meaning.

This includes mapping parser output `restrictions` into `injury_restrictions` so the same restriction truth is preserved downstream.

## 5) `athlete_model.py` passes injury fields into Stage 2
`athlete_model.py` is responsible for forwarding injury fields into Stage 2 payload construction so downstream logic receives the same structured injury truth.

This includes forwarding `injury_restrictions` (mapped from parser `restrictions`) into Stage 2 inputs.

## 6) `sparring_advisories.py` precedence
`sparring_advisories.py` must read structured injury entries first.

If structured entries are absent or insufficient, raw injury text may be used as fallback.

## 7) `injury_guard` / filtering for exercise exclusion
Injury guard/filtering logic applies injury restrictions to exclude unsafe exercises and training elements.

This exclusion behavior must follow structured injury restrictions first, with raw-text-derived behavior only when structured data is unavailable.

## 8) `rehab_protocols` for rehab drill selection
`rehab_protocols` selects rehab-oriented drills based on injury context and restrictions.

Selection should be driven by structured/guided injury information first, with raw-text fallback only when necessary.

---

## Non-negotiable precedence rule
Across all stages above:
- Structured and guided injury data has higher authority than raw injury text.
- Raw injury reparsing is a secondary fallback path, not a peer source of truth.

No stage should downgrade an available structured injury signal in favor of raw prose interpretation.
