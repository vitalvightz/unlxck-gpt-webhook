# Personal exercise records: audit and implementation boundaries

- Existing `GET /api/history/exercises` returns log occurrences in pages of 50,
  sorted by day/update time/ID. The UI filters only loaded rows and shows a card
  for each occurrence. It cannot provide a complete movement index or best load.
- `exercise_logs.exercise_key` is a server-owned canonical bank-name key stamped
  before display copy is rewritten. Match its exact stored value across plans;
  never fuzzy-match names, remove variation qualifiers or infer missing keys.
- `block_id` identifies a prescription within a plan/day, not a movement across
  programmes. Legacy rows without a valid key remain separately labelled records
  addressed by their original log UUID, not invented exercise identities.
- `exercise_logs` survives plan deletion (`plan_id ON DELETE SET NULL`). These
  orphaned logs retain their own frozen prescriptions and actuals. No plan read,
  session-completion join or current-bank reconstruction is necessary.
- Performed entries require explicit `as_prescribed`, or `modified` with valid
  nonempty actuals. Skips, explicit zero-work results and unknown results cannot
  establish a library achievement or best. Nonphysical/rehab blocks stay outside
  this exercise-log surface; rehab evidence remains in Session Details.
- Best loads use positive actual kg/lb values, or an unambiguous numeric kg/lb
  prescription explicitly confirmed as prescribed. No parsing display strings,
  percentages, body mass, rep ranges or estimated 1RM. Each unit has its own max;
  kg and lb are never compared as raw numbers or silently converted.
- Only confirmed-as-prescribed results can fill absent performance fields from
  their own frozen numeric prescription. Modified results never receive missing
  prescribed numbers. Detail columns keep explicit actuals separate throughout.

## Query approach

No schema migration or duplicate logging system. On first opening Exercises,
the API derives a lightweight index from owner-scoped existing logs, reading
bounded batches and retaining one summary per canonical key plus eligible legacy
record locators. Search uses that complete summary index, not the latest 50 logs.
Raw lifetime logs never go to the browser. This is an O(retained logs) server read
per index refresh, not a materialized index; large-scale SQL aggregation can be
reviewed separately if actual volume warrants it.

The scan has an insertion-time cutoff and advances by immutable log UUID until
an empty page, including when PostgREST returns fewer rows than requested. A
failed/malformed page fails the entire index instead of claiming a partial best.
The existing owner/day index and primary/occurrence keys were confirmed read-only
in connected Supabase. No database changes were made.

Selected history loads on demand with exact owner/key (or owner/log UUID) filters.
Keyset pagination uses immutable `(training_day, id)`, with the same insertion
cutoff; update-time corrections cannot reorder pages into duplicate entries.
Index and detail pages stay in memory for the signed-in History visit and reset
on account/consent changes. Notes and pain reasons follow current health consent,
using PR #2940's sanitized, read-only block projection.

## Limits

"Best recorded load" means highest eligible retained log, not a lifetime PR or
equivalent strength across rep schemes. Deleted logs cannot be recovered. Legacy
entries without keys cannot safely be deduplicated across dates; they remain in
an explicit unlinked-record section. Updates made elsewhere during the visit
require a refresh to rebuild cached summaries. No individual-set results exist
and none are manufactured.
