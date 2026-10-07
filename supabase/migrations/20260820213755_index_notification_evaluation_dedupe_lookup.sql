-- The deferred-event sweep asks one exact question per source event: has this
-- profile/dedupe key already recorded this decision? Without a matching index
-- that existence check degrades into a scan of the profile's whole evaluation
-- history on every ten-minute worker sweep. The same index serves the
-- dedupe-key reads the observe-mode arbitration already performs.
--
-- Additive only: no table, function, grant, or prior migration is changed.

create index if not exists notification_evaluations_dedupe_decision_idx
  on public.notification_evaluations (profile_id, dedupe_key, decision)
  where dedupe_key is not null;
