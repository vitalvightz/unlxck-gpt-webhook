-- Keep the athlete's current explicit health-data consent choice as a direct,
-- server-owned boolean alongside the existing audit timestamps.

begin;

alter table public.profiles
  add column if not exists health_data_consent boolean not null default false;

update public.profiles
set health_data_consent = true
where health_consent_at is not null
  and (
    health_consent_withdrawn_at is null
    or health_consent_at > health_consent_withdrawn_at
  );

comment on column public.profiles.health_data_consent is
  'Current explicit health-data consent choice. Server-owned and stored with the grant or withdrawal timestamp.';

create or replace function private.prevent_client_compliance_writes()
returns trigger
language plpgsql
set search_path = pg_catalog, pg_temp
as $$
begin
  if auth.role() <> 'service_role' then
    if tg_op = 'INSERT' then
      if new.date_of_birth is not null
        or new.terms_version is not null
        or new.terms_accepted_at is not null
        or new.health_data_consent is true
        or new.health_consent_version is not null
        or new.health_consent_at is not null
        or new.health_consent_withdrawn_at is not null then
        raise exception 'Consent and date of birth are set by the backend only.';
      end if;
    elsif tg_op = 'UPDATE' then
      if new.date_of_birth is distinct from old.date_of_birth
        or new.terms_version is distinct from old.terms_version
        or new.terms_accepted_at is distinct from old.terms_accepted_at
        or new.health_data_consent is distinct from old.health_data_consent
        or new.health_consent_version is distinct from old.health_consent_version
        or new.health_consent_at is distinct from old.health_consent_at
        or new.health_consent_withdrawn_at is distinct from old.health_consent_withdrawn_at then
        raise exception 'Consent and date of birth are set by the backend only.';
      end if;
    end if;
  end if;

  return new;
end;
$$;

commit;
