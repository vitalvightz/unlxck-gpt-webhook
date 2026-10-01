-- Fix every signup that carries a date of birth failing with
-- "Database error saving new user".
--
-- 20260817120000_add_compliance_age_and_consent wrote the age check as
-- current_date qualified with the pg_catalog schema. CURRENT_DATE is an SQL keyword, not a function, so
-- it cannot be schema-qualified: Postgres reads the qualified form as a
-- column of a table named pg_catalog and fails with 42P01 "missing FROM-clause
-- entry for table pg_catalog". PL/pgSQL only plans that line once a signup
-- actually supplies date_of_birth metadata, which the unlxck.com signup form
-- always does, so every web signup was rejected.
--
-- Bare current_date is safe under search_path = pg_catalog: it is parsed as a
-- keyword and never resolved through the search path.

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

  if declared_dob > (current_date - interval '13 years') then
    raise exception using
      errcode = 'P0001',
      message = 'under_minimum_age',
      detail = 'UNLXCK accounts are for athletes aged 13 or over.';
  end if;

  return new;
end;
$$;

revoke all on function private.enforce_auth_signup_minimum_age() from public, anon, authenticated;
