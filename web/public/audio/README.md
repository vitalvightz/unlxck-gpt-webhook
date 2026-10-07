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
| `crowd-amateur.mp3` | [G29-44-Fight Crowd Yelling.wav](https://freesound.org/people/craigsmith/sounds/438404/) ("Mixed group fight crowd. Boxing match."), 3–63 s | craigsmith | CC0 1.0 |
| `crowd-professional.mp3` | [Boston Garden Celtics Ambience 2.m4a](https://freesound.org/people/Douglas711/sounds/424297/) ("TD Garden, Boston ambience"), 3–63 s | Douglas711 | CC0 1.0 |

Processing (ffmpeg): the steadiest 60 s window by momentary loudness, mono
44.1 kHz, the last 3 s crossfaded into the first 3 s for a seamless loop,
`loudnorm` to −20 LUFS, 96 kbps MP3. `crowd.ts` loops just inside the MP3
encoder padding.
