# Rehab YouTube preparation

Today now resolves approved exercise media for its current rehab blocks through the existing exercise_media service and ExerciseMediaProvider. The canonical rehab drill ID is the video identity; wording changes never select another movement. Media remains presentation metadata outside the prescription revision and frozen snapshot. Missing/unavailable clips leave the prescribed cues usable.

`rehab-video-curation.csv` contains 46 published physical rehab identities and their exact prescription instructions, including the five pilot additions (the shoulder wall slide already had a row). It excludes dormant bank candidates and CALM activity-modification guidance. Every URL is blank: these rows are preparation, not video approval. There are no public data writes, migrations, new video player, or new video table.

## Curation workflow

1. Find a clip matching the exact movement, support, range and resistance in review_context. Keep aliases empty unless identical mechanics are established; a shared family/name is insufficient.
2. Use the existing tools/exercise_media.py review workflow to propose clips and suitable loop segments. A person must approve each movement by filling youtube_url; automated review alone does not publish it.
3. With existing service credentials configured, run tools/exercise_media.py import docs/rehab-video-curation.csv --dry-run, inspect results, then import approved rows through the existing tool. It checks availability, embedding, age restrictions and loop bounds. Never commit credentials.
4. Verify clips in Today using the existing thumbnail/YouTube nocookie player. The usual media availability sweep handles unavailable videos.

### Attach a reviewed URL to an existing bank exercise

Find the exercise's `rehab_drill_id` in today's live prescription or its `id`
in `data/rehab_bank.json`. Use the corresponding **exact** `exercise_key` row in
`docs/rehab-video-curation.csv`. For example, bank ID
`chest_strain_comfortable_movement` uses media key
`chest-strain-comfortable-movement`. Do not edit the bank or its clinical hashes.

Fill that row's `youtube_url` with the reviewed watch URL
(`https://www.youtube.com/watch?v=<11-character-video-id>`), short link
(`https://youtu.be/<11-character-video-id>`) or Shorts URL
(`https://www.youtube.com/shorts/<11-character-video-id>`). Optional `start_s`
and `end_s` identify the demonstration segment. Keep the other identity and
review context columns intact, and leave `aliases` empty for a rehab-specific
movement.

```powershell
python tools/exercise_media.py import docs/rehab-video-curation.csv --dry-run
python tools/exercise_media.py import docs/rehab-video-curation.csv
```

The existing importer validates the video and saves its parsed `video_id` and
segment in `public.exercise_media`; no schema change or bank activation is
required. Use the existing backend service credentials and YouTube Data API key
in your local environment. Credentials belong outside the CSV and repository.
The serving index caches media for up to five minutes. Refresh Today after it
expires to see the clip on existing plans without regeneration.

Missing or invalid media leaves the exercise instructions and prescription
usable. The shared player's embedding-error state offers **Watch on YouTube**
and retains the instructions below it. A demo never changes the exercise's
approved range, resistance, restrictions, dose or completion/progression result.

## First LOAD clips to review

- Achilles: floor-level controlled lowering, bodyweight, stable support. Despite the historical drill ID containing `on_step`, the approved prescription is floor-level only. Reject step/drop, excessive dorsiflexion and weighted demonstrations.
- Lateral elbow: palm-down table-supported forearm, empty hand, comfortable wrist range within clinician restrictions, slow five-second lowering. Reject dumbbells, bands, forceful grip and forced end range.
- Ankle sprain: chair-seated bilateral heel raise and slow lowering on the floor. Reject standing, step, weights, bands, knee pressure and forced range. Keep the prescribed once-daily 1 × 10 cap.

A video illustrates mechanics; it cannot expand permission, dose, exercise selection or clinical eligibility. These LOAD clips are pending review; no URL is assigned by this PR.
