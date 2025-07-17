# Mental Training Module

This project scores mental drills so athletes get targeted practice. It parses questionnaire responses into tags and ranks drills using those tags.

Run the module to generate a basic plan starting today:

```bash
python -m mental.program
```

## Overview

The scoring engine compares each drill to an athlete's traits, weaknesses and current training phase. The higher the score, the more closely the drill fits that athlete right now.

## How Scoring Works

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

These values stack in order, but no single rule can exceed its cap.

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

## Exporting to Google Docs

`mental.main.handler()` can create an athlete plan in Google Docs. Provide your service account credentials as a Base64 string and the ID of a Drive folder you own:

```python
link = handler(
    form_payload,
    os.environ["GOOGLE_CREDS_B64"],
    os.environ.get("TARGET_FOLDER_ID"),
    debug=os.environ.get("DEBUG") == "1",
)
```

The document is first created by the service account and then moved into the specified folder so you retain ownership.
Set the environment variable `DEBUG=1` to print detailed progress and Google API errors when generating plans.
