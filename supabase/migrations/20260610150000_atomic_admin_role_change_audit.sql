-- Atomic admin role change + audit.
--
-- set_profile_role previously updated profiles.role and inserted the
-- admin_role_audit row in two separate statements; an audit-insert failure was
-- only logged, leaving a committed role change with no audit record. This RPC
-- performs both writes in one transaction so a role change can never commit
-- without its audit row. The deploy gate already requires admin_role_audit to
-- exist, so failing closed no longer risks blocking role changes on an
-- unmigrated environment.
--
-- Policy checks (last-admin lockout, idempotent no-op short-circuit) stay in
-- the application (api/store.py::set_profile_role); this function guards the
-- transition itself: the target row is locked, the caller's expected previous
-- role is CAS-checked, and the audit row records the authoritative
-- locked-row role.
--
-- Rollback notes:
--   drop function if exists public.set_profile_role_with_audit(uuid, text, text, text, text, text);
--   (api/store.py would need to be reverted to the two-statement write first.)

create or replace function public.set_profile_role_with_audit(
  p_athlete_id uuid,
  p_new_role text,
  p_actor text,
  p_expected_previous_role text default null,
  p_reason text default null,
  p_target_email text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile public.profiles%rowtype;
  v_new_role text := lower(btrim(p_new_role));
  v_actor text := nullif(btrim(p_actor), '');
  v_previous_role text;
  v_target_email text;
  v_action text;
begin
  if v_new_role not in ('admin', 'athlete') then
    raise exception 'unsupported_profile_role:%', p_new_role
      using errcode = 'P0001';
  end if;

  if v_actor is null then
    raise exception 'missing_role_change_actor:%', p_athlete_id
      using errcode = 'P0001';
  end if;

  select *
  into v_profile
  from public.profiles
  where id = p_athlete_id
  for update;

  if not found then
    raise exception 'profile_missing:%', p_athlete_id
      using errcode = 'P0002';
  end if;

  v_previous_role := coalesce(v_profile.role::text, 'athlete');

  -- CAS guard: the caller decided on the change after reading this role; a
  -- concurrent change means their decision (and audit previous_role) would be
  -- stale, so refuse instead of recording a misleading trail.
  if p_expected_previous_role is not null
    and v_previous_role <> lower(btrim(p_expected_previous_role)) then
    raise exception 'stale_profile_role:% expected %, got %',
      p_athlete_id, p_expected_previous_role, v_previous_role
      using errcode = 'P0001';
  end if;

  if v_previous_role = v_new_role then
    return jsonb_build_object(
      'athlete_id', v_profile.id,
      'email', lower(btrim(coalesce(v_profile.email, p_target_email, ''))),
      'previous_role', v_previous_role,
      'new_role', v_new_role,
      'changed', false
    );
  end if;

  v_target_email := coalesce(
    nullif(lower(btrim(v_profile.email)), ''),
    nullif(lower(btrim(p_target_email)), '')
  );
  if v_target_email is null then
    raise exception 'missing_role_change_target_email:%', p_athlete_id
      using errcode = 'P0001';
  end if;

  v_action := case when v_new_role = 'admin' then 'promote' else 'revoke' end;

  update public.profiles
  set role = v_new_role::public.app_role
  where id = p_athlete_id;

  -- Same transaction as the role update: if this insert fails, the role
  -- change rolls back with it.
  insert into public.admin_role_audit (
    target_athlete_id,
    target_email,
    previous_role,
    new_role,
    action,
    actor,
    reason
  )
  values (
    p_athlete_id,
    v_target_email,
    v_previous_role::public.app_role,
    v_new_role::public.app_role,
    v_action,
    v_actor,
    p_reason
  );

  return jsonb_build_object(
    'athlete_id', v_profile.id,
    'email', v_target_email,
    'previous_role', v_previous_role,
    'new_role', v_new_role,
    'action', v_action,
    'changed', true
  );
end;
$$;

revoke all on function public.set_profile_role_with_audit(uuid, text, text, text, text, text) from public;
revoke all on function public.set_profile_role_with_audit(uuid, text, text, text, text, text) from anon;
revoke all on function public.set_profile_role_with_audit(uuid, text, text, text, text, text) from authenticated;
grant execute on function public.set_profile_role_with_audit(uuid, text, text, text, text, text) to service_role;
