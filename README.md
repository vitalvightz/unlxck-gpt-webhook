# Mental Training Module

This repository turns questionnaire responses into customized mental drill plans. It normalizes raw form fields into tags, scores each drill in `Drills_bank.json`, and builds a phase‑based program that can be exported to Google Docs.

## Setup

Use Python 3 and install the required packages:

```bash
pip install -r requirements.txt
```

Run the unit tests to ensure everything works:

```bash
pytest -q
```

## Running

`mental/main.py` provides a small CLI used during development. It loads `tests/test_payload.json` as sample input and requires a base64‑encoded Google credentials string in `GOOGLE_CREDS_B64` to create a document.

```bash
export GOOGLE_CREDS_B64="..."  # service account credentials
python -m mental.main
```

For basic scoring without exporting you can import the modules directly:

```python
from mental.program import parse_mindcode_form
from mental.tags import map_tags
from mental.scoring import score_drills

fields = {...}  # dict matching the Google form
parsed = parse_mindcode_form(fields)
tags = map_tags(parsed)
results = score_drills(DRILL_BANK, tags, parsed["sport"], parsed["mental_phase"])
```

## Data Flow

1. **`program.parse_mindcode_form`** – extracts structured values from form fields and resolves the training phase.
2. **`tags.map_tags`** – maps those values to the controlled vocabulary in `tags.txt` and normalizes synonyms.
3. **`scoring.score_drills`** – applies the rules below to produce a score for each drill. Drills are filtered by sport and sorted by their final score.
4. **`main.build_plan_output`** – groups the top drills by phase and injects coach notes when contradictory tags are detected.

## Scoring Rules

Scores start at **1.0**. The adjustments below raise or lower the final number. Each rule has a hard limit so you know exactly how far it can move the score.

| Rule | Weight | Cap |
| ---- | ------ | --- |
| Base trait | +0.3 each | **+1.2** combined |
| Elite trait tier&nbsp;2 | +0.6 each | |
| Elite trait tier&nbsp;1 | +0.7 each | |
| Phase match | +0.5 | |
| Sport match | +0.3 | |
| High intensity penalty | -0.5 in TAPER, -0.2 in GPP | |
| Weakness match | +0.1 (+0.05 for each extra tag) | |
| Preferred modality reinforcement | +0.1 | |
| Modality synergy pair | +0.2 | |
| Elite trait without synergy | -0.2 | |
| Phase synergy bonus | cue +0.07, modality +0.05, theme +0.03 | **+0.15** |
| Sport-specific micro weights | ±0.2 each | **±0.4** total |
| Overload penalty | -0.1 per flag | **-0.5** total |
| CNS stress drill tag penalty | -0.1 | |

These values stack in order, but no single rule can exceed its cap. General relevance without overlapping tags earns nothing – precision is rewarded.

## Contradiction Detection

`contradictions.py` defines tag pairs that signal mismatches in an athlete's answers (e.g. claiming fast decisions yet overthinking). When any pair is present the generated plan highlights a **COACH REVIEW FLAG** with a brief note.

## Customization

- **Drills** – add or edit entries in `mental/Drills_bank.json` following the structure defined at the bottom of `tags.txt`.
- **Tags** – extend `tags.txt` and update `TAG_NORMALIZATION_MAP` in `normalization.py` for synonyms.
- **Scoring** – adjust weights in `scoring.py` such as `TRAIT_SCORES`, `SYNERGY_LIST` or the micro‑weight logic.

## Design Principle

The module assumes clear, tagged data. If a drill or athlete input does not explicitly match, it stays near the base score so that only the best‑fitting drills rise to the top.
