-- Age band, Terms acceptance and health-data consent.
--
-- Three server-owned facts land on the profile:
--
--   * date_of_birth        — the only source of the athlete's age band. The
--                            client never asserts "I am an adult"; it supplies a
--                            date and the server decides.
--   * terms_*              — which version of the Terms was accepted, and when.
--   * health_consent_*     — Article 9(2)(a) explicit consent for health data,
--                            recorded separately from the Terms and
--                            withdrawable, per docs/health-data-lawful-basis-dpia.md.
--
-- private_trial_ack_at is left alone. It evidences a different thing (that a
-- tester read the trial briefing), carries no document version, and must not be
-- pressed into service as consent for either document.

alter table public.profiles
  add column if not exists date_of_birth date,
  add column if not exists terms_version text,
  add column if not exists terms_accepted_at timestamptz,
  add column if not exists health_consent_version text,
  add column if not exists health_consent_at timestamptz,
  add column if not exists health_consent_withdrawn_at timestamptz;

comment on column public.profiles.date_of_birth is
  'Athlete-declared date of birth. The sole input to the server-derived age band; under-13 is rejected. Never accept a client-supplied is_minor flag in its place.';
comment on column public.profiles.terms_version is
  'Version string of the Terms of Use the athlete accepted. Null until accepted.';
comment on column public.profiles.terms_accepted_at is
  'Server-stamped UTC time of Terms acceptance. Null until accepted.';
comment on column public.profiles.health_consent_version is
  'Version string of the health-data consent wording the athlete agreed to.';
comment on column public.profiles.health_consent_at is
  'Server-stamped UTC time of explicit health-data consent (UK GDPR Art. 9(2)(a)). Null until given.';
comment on column public.profiles.health_consent_withdrawn_at is
  'Server-stamped UTC time consent was withdrawn. Consent is active only while this is null or older than health_consent_at.';

-- Sanity bound only. The real 13+ rule needs current_date, which a CHECK
-- constraint cannot use (check expressions must be immutable), so it is
-- enforced by the triggers below instead.
do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_date_of_birth_plausible'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_date_of_birth_plausible
      check (date_of_birth is null or date_of_birth > date '1900-01-01');
  end if;
end
$$;

-- Consent evidence is only evidence if the subject cannot write it themselves.
-- profiles_self_update lets a browser client update its own row, so without this
-- an athlete could stamp their own terms_accepted_at, backdate a consent, or
-- edit their date of birth out of the under-18 band. Mirrors the existing
-- prevent_self_role_escalation / prevent_username_policy_bypass pattern: the
-- service-role backend is the only sanctioned writer.
create or replace function public.prevent_client_compliance_writes()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.role() <> 'service_role' then
    if tg_op = 'INSERT' then
      if new.date_of_birth is not null
        or new.terms_version is not null
        or new.terms_accepted_at is not null
        or new.health_consent_version is not null
        or new.health_consent_at is not null
        or new.health_consent_withdrawn_at is not null then
        raise exception 'Consent and date of birth are set by the backend only.';
      end if;
    elsif tg_op = 'UPDATE' then
      if new.date_of_birth is distinct from old.date_of_birth
        or new.terms_version is distinct from old.terms_version
        or new.terms_accepted_at is distinct from old.terms_accepted_at
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

drop trigger if exists profiles_prevent_client_compliance_writes on public.profiles;
create trigger profiles_prevent_client_compliance_writes
before insert or update on public.profiles
for each row
execute function public.prevent_client_compliance_writes();

-- The 13+ floor, applied to every writer including the service role. The API
-- rejects an under-13 date of birth with a clean error; this is the backstop
-- that makes it impossible to store one at all.
create or replace function public.enforce_profile_minimum_age()
returns trigger
language plpgsql
as $$
begin
  if new.date_of_birth is not null
    and new.date_of_birth > (current_date - interval '13 years') then
    raise exception 'under_minimum_age'
      using detail = 'UNLXCK accounts require an athlete aged 13 or over.';
  end if;

  return new;
end;
$$;

drop trigger if exists profiles_enforce_minimum_age on public.profiles;
create trigger profiles_enforce_minimum_age
before insert or update of date_of_birth on public.profiles
for each row
execute function public.enforce_profile_minimum_age();

-- Reject an under-13 signup inside Postgres, so the rule still holds when a
-- caller bypasses unlxck.com and posts to /auth/v1/signup directly. Mirrors the
-- existing enforce_auth_signup_rate_limit guard.
--
-- A signup that carries no date_of_birth metadata is allowed through here on
-- purpose: magic-link invites and admin-created accounts have no signup form to
-- collect one. Those accounts cannot get past the API's compliance gate without
-- supplying a date of birth, and the profile trigger above still rejects an
-- under-13 one.
create or replace function private.enforce_auth_signup_minimum_age()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  declared_dob_text text;
  declared_dob date;
begin
  declared_dob_text := nullif(btrim(coalesce(new.raw_user_meta_data ->> 'date_of_birth', '')), '');

  if declared_dob_text is null then
    return new;
  end if;

  begin
    declared_dob := left(declared_dob_text, 10)::date;
  exception when others then
    raise exception using
      errcode = 'P0001',
      message = 'date_of_birth_invalid',
      detail = 'Date of birth must be supplied as YYYY-MM-DD.';
  end;

  if declared_dob > (pg_catalog.current_date - interval '13 years') then
    raise exception using
      errcode = 'P0001',
      message = 'under_minimum_age',
      detail = 'UNLXCK accounts are for athletes aged 13 or over.';
  end if;

  return new;
end;
$$;

revoke all on function private.enforce_auth_signup_minimum_age() from public, anon, authenticated;

drop trigger if exists enforce_auth_signup_minimum_age on auth.users;
create trigger enforce_auth_signup_minimum_age
before insert on auth.users
for each row
execute function private.enforce_auth_signup_minimum_age();
