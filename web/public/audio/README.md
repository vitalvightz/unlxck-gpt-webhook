# Guided visualisation crowd loops

The guided Fight Visualisation plays a crowd under the voice
(`web/lib/fight-visualisation/crowd.ts`). It looks for:

| File | Athlete | Sound |
|---|---|---|
| `crowd-amateur.mp3` | `professional_status` amateur (or unset) | Small hall: scattered voices, corner shouts, sparse claps |
| `crowd-professional.mp3` | `professional_status` professional | Arena: steady roar and murmur |

A missing file is not an error: the crowd toggle simply does not appear.

## Requirements

- **Licence: CC0 only** (e.g. Freesound with the "Creative Commons 0" filter).
  Record each source in the table below.
- 45–90 s, seamless loop (trim on a quiet moment, short crossfade), mono or
  stereo, 96–128 kbps MP3, normalised to about −20 LUFS so it sits well under
  the voice. Under ~1 MB each.
- No announcer, ring card or music: words in the bed compete with the guide.

## Sources

| File | Source | Author | Licence |
|---|---|---|---|
| `crowd-amateur.mp3` | _pending_ | | CC0 |
| `crowd-professional.mp3` | _pending_ | | CC0 |
