# Rehab YouTube preparation

Today now resolves approved exercise media for its current rehab blocks through the existing exercise_media service and ExerciseMediaProvider. The canonical rehab drill ID is the video identity; wording changes never select another movement. Media remains presentation metadata outside the prescription revision and frozen snapshot. Missing/unavailable clips leave the prescribed cues usable.

`rehab-video-curation.csv` contains 41 active physical rehab identities and their exact prescription instructions. It deliberately excludes dormant bank candidates and CALM activity-modification guidance. Every URL is blank: these rows are preparation, not video approval. There are no public data writes, migrations, new video player, or new video table.

## Curation workflow

1. Find a clip matching the exact movement, support, range and resistance in review_context. Keep aliases empty unless identical mechanics are established; a shared family/name is insufficient.
2. Use the existing tools/exercise_media.py review workflow to propose clips and suitable loop segments. A person must approve each movement by filling youtube_url; automated review alone does not publish it.
3. With existing service credentials configured, run tools/exercise_media.py import docs/rehab-video-curation.csv --dry-run, inspect results, then import approved rows through the existing tool. It checks availability, embedding, age restrictions and loop bounds. Never commit credentials.
4. Verify clips in Today using the existing thumbnail/YouTube nocookie player. The usual media availability sweep handles unavailable videos.

## First LOAD clips to review

- Achilles: floor-level controlled lowering, bodyweight, stable support. Despite the historical drill ID containing `on_step`, the approved prescription is floor-level only. Reject step/drop, excessive dorsiflexion and weighted demonstrations.
- Lateral elbow: palm-down table-supported forearm, empty hand, comfortable assessed wrist range, slow five-second lowering. Reject dumbbells, bands, forceful grip and forced end range.

A video illustrates mechanics; it cannot expand permission, dose, exercise selection or clinical eligibility. Neither LOAD clip is assigned yet.
