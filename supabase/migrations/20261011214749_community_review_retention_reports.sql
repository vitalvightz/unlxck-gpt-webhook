-- Corrective migration; the applied Stage B migration remains immutable.
alter table public.community_exercise_revisions add column changes_requested_at timestamptz;
-- Existing correction requests receive the full grace period from this rollout.
update public.community_exercise_revisions set changes_requested_at=now() where status='changes_requested';
create function public.community_correction_window() returns trigger
language plpgsql security invoker set search_path='' as $$
begin
  if TG_OP='UPDATE' then
    if new.status='changes_requested' and old.status is distinct from new.status then new.changes_requested_at:=now();
    elsif new.status='private' and not exists(select 1 from public.community_exercises where id=new.exercise_id and attribution_consent) then new.changes_requested_at:=null; end if;
  elsif new.status='private' then
    select r.changes_requested_at into new.changes_requested_at from public.community_exercises e
      join public.community_exercise_revisions r on r.id=e.current_revision_id
      where e.id=new.exercise_id and r.status in('changes_requested','private');
  end if;
  return new;
end $$;
revoke all on function public.community_correction_window() from public,anon,authenticated;
grant execute on function public.community_correction_window() to service_role;
create trigger community_correction_window before insert or update on public.community_exercise_revisions
for each row execute function public.community_correction_window();

create or replace function public.community_media_retained(p_media_id uuid) returns boolean
language sql security invoker set search_path='' as $$
  select exists(select 1 from public.community_exercise_revisions r join public.community_exercises e on e.id=r.exercise_id
    where r.media_id=p_media_id and ((e.current_revision_id=r.id and (r.status='in_review' or (r.status in('changes_requested','private') and r.changes_requested_at>now()-interval '30 days')))
      or (e.published_revision_id=r.id and e.attribution_consent and e.creator_id is not null)
      or exists(select 1 from public.custom_training_plans p cross join lateral jsonb_array_elements(p.sessions) s
        cross join lateral jsonb_array_elements(s->'exercises') x where x->>'community_revision_id'=r.id::text)));
$$;
revoke all on function public.community_media_retained(uuid) from public,anon,authenticated;
grant execute on function public.community_media_retained(uuid) to service_role;


-- Resolve one report without changing publication, consent, content or verification.
create function public.community_dismiss_report(p_actor_id uuid,p_revision_id uuid,p_report_id uuid,p_reason text) returns uuid
language plpgsql security invoker set search_path='' as $$
declare e public.community_exercises; report public.community_exercise_reports;
begin
  if not exists(select 1 from public.profiles where id=p_actor_id and role='admin' and access_status='approved') then raise exception 'community forbidden' using errcode='42501'; end if;
  if nullif(btrim(p_reason),'') is null or char_length(p_reason)>1000 then raise exception 'decision reason required'; end if;
  select x.* into e from public.community_exercises x join public.community_exercise_revisions r on r.exercise_id=x.id where r.id=p_revision_id for update of x;
  select x.* into report from public.community_exercise_reports x join public.community_exercise_revisions r on r.id=x.revision_id where x.id=p_report_id and r.exercise_id=e.id for update of x;
  if e.id is null or report.id is null then raise exception 'community not found' using errcode='P0002'; end if;
  if report.status='resolved' then return e.current_revision_id; end if;
  update public.community_exercise_reports set status='resolved' where id=report.id;
  insert into public.community_exercise_audit(exercise_id,revision_id,actor_id,action,details)
    values(e.id,report.revision_id,p_actor_id,'dismiss_report',jsonb_build_object('report_id',report.id,'reason',btrim(p_reason)));
  return e.current_revision_id;
end $$;
revoke all on function public.community_dismiss_report(uuid,uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.community_dismiss_report(uuid,uuid,uuid,text) to service_role;
