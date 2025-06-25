# Mental Training Programme

This repository contains utilities for parsing mental performance forms and
generating short training plans. It focuses on mapping questionnaire responses
into structured tags that can be used to build mindfulness, visualisation and
journaling drills.

Run the module as a script to print a default plan starting today:

```bash
python -m mental.program
```

## Code overview

- `mental/program.py` – parses data from the *Mindcode* form and returns a
  dictionary of clean field values.
- `mental/map_mindcode_tags.py` – converts the parsed fields into normalised
  mental performance tags such as `breath_pattern`, `reset_speed` and
  `motivation_type`.
- `mental/tags.py` – an alternative mapping helper used by
  `map_tags.py`.
- `tags.txt` – lists all available tags and shows how a drill can reference
  them.
- `tests/` – unit tests covering the tag-mapping logic.

## Potential with mental drills injected

By defining drills with the tags in `tags.txt`, the mapping functions can
automatically match an athlete's responses to relevant exercises. Injecting new
drills allows coaches to expand the programme and create targeted routines –
for example, providing decisiveness drills to players who hesitate under
pressure. As more drills are added, the system can produce customised mental
training plans across different sports.
