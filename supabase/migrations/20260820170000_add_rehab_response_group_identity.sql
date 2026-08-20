-- One injury-level athlete answer may describe several drill exposures. Keep a
-- queryable shared identity so downstream evidence readers do not count copied
-- response fields as independently assessed responses.
--
-- Older rows cannot be reconstructed into true historical groups because the
-- previous event did not store plan/session response provenance. Giving each
-- one its own group is the conservative backfill: it never falsely groups two
-- independently unknown legacy observations.
update public.rehab_exposures
set event_json = jsonb_set(
  event_json,
  '{response_group_id}',
  to_jsonb(id::text),
  true
)
where nullif(event_json->>'response_group_id', '') is null;

alter table public.rehab_exposures
  add column if not exists response_group_id uuid
    generated always as ((event_json->>'response_group_id')::uuid) stored;

alter table public.rehab_exposures
  alter column response_group_id set not null;

create index if not exists rehab_exposures_response_group_idx
  on public.rehab_exposures (athlete_id, response_group_id);

comment on column public.rehab_exposures.response_group_id is
  'Server-owned deterministic identity for one injury-level athlete response shared by its drill exposures.';
