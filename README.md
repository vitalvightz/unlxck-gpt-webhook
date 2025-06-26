# Mental Training Module

This project scores mental drills so athletes get targeted practice. It parses questionnaire responses into tags and ranks drills using those tags.

Run the module to generate a basic plan starting today:

```bash
python -m mental.program
```

## Overview

The scoring engine compares each drill to an athlete's traits, weaknesses and current training phase. The higher the score, the more closely the drill fits that athlete right now.

## How Scoring Works

- **Trait scores** – Each raw trait adds a set value: base traits +0.3, elite tier&nbsp;2 +0.5, elite tier&nbsp;1 +0.7. Scores from traits cap at +1.2.
- **Phase & intensity logic** – A drill matching the athlete's phase gives +0.5. High intensity can deduct up to -0.5 if the athlete is tapering or early in GPP. Fighters in camp skip these penalties.
- **Weakness match bonus** – When drill tags hit an athlete's listed weaknesses, the score climbs by +0.1 plus +0.05 for each extra match. If the drill also uses a preferred modality, add another +0.1.
- **Preferred modality reinforcement** – See above; it nudges the score only when a weakness match is found.
- **Modality synergy pairs** – Certain modality combos give +0.2 if the athlete has required tags (for example, visualisation + breathwork when the athlete needs quick resets).
- **Sport-specific micro-weights** – Small adjustments (±0.2 each) reward drills that fit common patterns in sports like boxing, football or track.
- **Overload penalties** – High intensity or overload tags drop the score up to -0.5 when tapering or when an athlete shows CNS fragility.

## What's NOT scored

General relevance without tagged overlap earns nothing. The system only rewards clear tag matches.

## Customization

Edit `mental/scoring.py` to tweak values:

- Update `TRAIT_SCORES` for different trait weights.
- Change `SYNERGY_LIST` to redefine modality pairs and required tags.
- Adjust `sport_microweight_bonus()` for sport-specific tweaks.

You can also expand the tag list in `tags.txt` or modify which tags count as weaknesses.

## Design Principle

The system only rewards precision. If a drill doesn't clearly match tagged needs, it stays near the base score.
