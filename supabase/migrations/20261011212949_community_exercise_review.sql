-- Stage B: immutable community revisions, service-only transitions and audited publication.
create table public.community_exercises (
  id uuid primary key default gen_random_uuid(),
  creator_id uuid references public.profiles(id) on delete set null,
  current_revision_id uuid,
  published_revision_id uuid,
  attribution_consent boolean not null default false,
  consent_at timestamptz,
  withdrawn_at timestamptz,
  created_at timestamptz not null default now()
);
create index community_exercises_creator_idx on public.community_exercises(creator_id);
create table public.community_exercise_revisions (
  id uuid primary key default gen_random_uuid(),
  exercise_id uuid not null references public.community_exercises(id) on delete cascade,
  name text not null check(char_length(btrim(name)) between 1 and 100),
  equipment text check(char_length(equipment)<=120),
  notes text check(char_length(notes)<=2000),
  media_id uuid references public.private_exercise_media(id) on delete set null,
  status text not null default 'private' check(status in ('private','in_review','changes_requested','rejected','published','superseded')),
  submitted_at timestamptz,
  verified_at timestamptz,
  verified_by uuid references public.profiles(id) on delete set null,
  verified_media_id uuid,
  verified_proof jsonb,
  confirmed_at timestamptz,
  confirmed_by uuid references public.profiles(id) on delete set null,
  decision_reason text check(char_length(decision_reason)<=1000),
  created_at timestamptz not null default now(),
  unique(id,exercise_id)
);
alter table public.community_exercises add foreign key(current_revision_id,id) references public.community_exercise_revisions(id,exercise_id) deferrable initially deferred;
alter table public.community_exercises add foreign key(published_revision_id,id) references public.community_exercise_revisions(id,exercise_id) deferrable initially deferred;
create index community_revision_queue_idx on public.community_exercise_revisions(status,submitted_at);
create index community_revision_media_idx on public.community_exercise_revisions(media_id);
create table public.community_exercise_audit (
  id uuid primary key default gen_random_uuid(),
  exercise_id uuid not null references public.community_exercises(id) on delete cascade,
  revision_id uuid references public.community_exercise_revisions(id) on delete set null,
  actor_id uuid references public.profiles(id) on delete set null,
  action text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index community_audit_exercise_idx on public.community_exercise_audit(exercise_id,created_at);
create table public.community_exercise_reports (
  id uuid primary key default gen_random_uuid(),
  revision_id uuid not null references public.community_exercise_revisions(id) on delete cascade,
  reporter_id uuid references public.profiles(id) on delete set null,
  reason text not null check(char_length(btrim(reason)) between 1 and 1000),
  status text not null default 'open' check(status in ('open','resolved')),
  created_at timestamptz not null default now(),
  unique(revision_id,reporter_id)
);
create index community_reports_revision_idx on public.community_exercise_reports(revision_id,status);
-- Index references used during account/media deletion and immutable-history retention.
create index community_revision_exercise_idx on public.community_exercise_revisions(exercise_id);
create index community_revision_verifier_idx on public.community_exercise_revisions(verified_by);
create index community_revision_confirmer_idx on public.community_exercise_revisions(confirmed_by);
create index community_exercises_current_idx on public.community_exercises(current_revision_id,id);
create index community_exercises_published_idx on public.community_exercises(published_revision_id,id);
create index community_audit_revision_idx on public.community_exercise_audit(revision_id);
create index community_audit_actor_idx on public.community_exercise_audit(actor_id,created_at);
create index community_reports_reporter_idx on public.community_exercise_reports(reporter_id,created_at);
alter table public.community_exercises enable row level security;
alter table public.community_exercise_revisions enable row level security;
alter table public.community_exercise_audit enable row level security;
alter table public.community_exercise_reports enable row level security;
revoke all on public.community_exercises,public.community_exercise_revisions,public.community_exercise_audit,public.community_exercise_reports from anon,authenticated;
grant all on public.community_exercises,public.community_exercise_revisions,public.community_exercise_audit,public.community_exercise_reports to service_role;

create function public.community_revision_available(p_revision_id uuid) returns boolean
language sql security invoker set search_path='' as $$
  select exists(select 1 from public.community_exercise_revisions r
    left join public.private_exercise_media m on m.id=r.media_id left join public.private_video_assets a on a.id=m.asset_id
    where r.id=p_revision_id and r.status='published' and r.verified_at is not null
      and r.verified_media_id is not distinct from r.media_id
      and (r.media_id is null or m.provider='youtube' or (m.provider='uploaded' and a.status='verified' and a.sha256=r.verified_proof->>'sha256')));
$$;
revoke all on function public.community_revision_available(uuid) from public,anon,authenticated;
grant execute on function public.community_revision_available(uuid) to service_role;

-- Always resolve attribution from the live consenting profile; never request data.
create function public.community_revision_payload(p_revision_id uuid) returns jsonb
language sql security invoker set search_path='' as $$
  select jsonb_build_object('id',e.id,'revision_id',r.id,'name',r.name,'equipment',r.equipment,'notes',r.notes,
    'media_id',r.media_id,'status',case when r.status='published' and e.published_revision_id is distinct from r.id then 'private' else r.status end,'submitted_at',r.submitted_at,'created_at',r.created_at,
    'reason',r.decision_reason,'verified',r.verified_at is not null,'confirmed',r.confirmed_at is not null,
    'has_publication',e.published_revision_id is not null,
    'published',coalesce(e.published_revision_id=r.id and e.attribution_consent and p.username is not null and public.community_revision_available(r.id),false),
    'contributor',case when e.attribution_consent and p.username is not null then
      jsonb_build_object('username',p.username,'avatar_url',p.avatar_url) else null end,
    'raw_media',case when m.id is null then null else to_jsonb(m)||jsonb_build_object('asset',to_jsonb(a)) end)
  from public.community_exercise_revisions r join public.community_exercises e on e.id=r.exercise_id
  left join public.profiles p on p.id=e.creator_id
  left join public.private_exercise_media m on m.id=r.media_id
  left join public.private_video_assets a on a.id=m.asset_id
  where r.id=p_revision_id;
$$;

create function public.community_detail(p_actor_id uuid,p_revision_id uuid,p_admin boolean default false) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare e public.community_exercises; r public.community_exercise_revisions;
begin
  if not exists(select 1 from public.profiles where id=p_actor_id and access_status='approved') then raise exception 'community forbidden' using errcode='42501'; end if;
  select * into r from public.community_exercise_revisions where id=p_revision_id;
  select * into e from public.community_exercises where id=r.exercise_id;
  if r.id is null then raise exception 'community not found' using errcode='P0002'; end if;
  if p_admin then
    if not exists(select 1 from public.profiles where id=p_actor_id and role='admin') then raise exception 'community forbidden' using errcode='42501'; end if;
  elsif e.creator_id is distinct from p_actor_id and not (
    (e.published_revision_id=r.id and public.community_revision_available(r.id) and e.attribution_consent and exists(select 1 from public.profiles where id=e.creator_id and username is not null))
    or (r.status='published' and exists(select 1 from public.custom_training_plans p
      cross join lateral jsonb_array_elements(p.sessions) s cross join lateral jsonb_array_elements(s->'exercises') x
      where p.athlete_id=p_actor_id and x->>'community_revision_id'=r.id::text))) then
    raise exception 'community not found' using errcode='P0002';
  end if;
  return public.community_revision_payload(r.id) || case when p_admin then jsonb_build_object(
    'audit',(select coalesce(jsonb_agg(to_jsonb(x) order by x.created_at),'[]') from public.community_exercise_audit x where x.exercise_id=e.id),
    'reports',(select coalesce(jsonb_agg(jsonb_build_object('id',x.id,'reason',x.reason,'status',x.status,'created_at',x.created_at) order by x.created_at),'[]') from public.community_exercise_reports x join public.community_exercise_revisions z on z.id=x.revision_id where z.exercise_id=e.id)) else '{}'::jsonb end;
end $$;

create function public.community_list(p_actor_id uuid,p_scope text,p_query text default '',p_offset integer default 0,p_limit integer default 30) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare ids uuid[]; total integer;
begin
  if not exists(select 1 from public.profiles where id=p_actor_id and access_status='approved') then raise exception 'community forbidden' using errcode='42501'; end if;
  if p_scope not in ('public','mine','review') then raise exception 'invalid community scope'; end if;
  if p_scope='review' and not exists(select 1 from public.profiles where id=p_actor_id and role='admin') then raise exception 'community forbidden' using errcode='42501'; end if;
  with candidates as (
    select r.id,r.created_at from public.community_exercises e
    join public.community_exercise_revisions r on r.id=case when p_scope='public' then e.published_revision_id else e.current_revision_id end
    left join public.profiles p on p.id=e.creator_id
    where (p_scope='mine' and e.creator_id=p_actor_id
      or p_scope='review' and ((r.status in ('in_review','changes_requested','rejected') or (r.status='published' and e.published_revision_id=r.id)) or exists(select 1 from public.community_exercise_reports x join public.community_exercise_revisions z on z.id=x.revision_id where z.exercise_id=e.id and x.status='open'))
      or p_scope='public' and e.attribution_consent and p.username is not null and public.community_revision_available(r.id))
      and (p_query='' or strpos(lower(r.name||' '||coalesce(r.equipment,'')),lower(left(p_query,100)))>0)
  ) select count(*)::integer, (select array_agg(id order by created_at desc,id) from (select * from candidates order by created_at desc,id offset greatest(p_offset,0) limit least(greatest(p_limit,1),50)) page)
    into total,ids from candidates;
  return jsonb_build_object('entries',(select coalesce(jsonb_agg(public.community_revision_payload(id) order by ord),'[]') from unnest(ids) with ordinality t(id,ord)),
    'total',total,'next_offset',case when greatest(p_offset,0)+least(greatest(p_limit,1),50)<total then greatest(p_offset,0)+least(greatest(p_limit,1),50) else null end);
end $$;

create function public.community_command(p_actor_id uuid,p_action text,p_payload jsonb) returns uuid
language plpgsql security invoker set search_path='' as $$
declare e public.community_exercises; r public.community_exercise_revisions; next_id uuid; actor_admin boolean; m public.private_exercise_media; a public.private_video_assets; proof jsonb;
begin
  if not exists(select 1 from public.profiles where id=p_actor_id and access_status='approved') then raise exception 'community forbidden' using errcode='42501'; end if;
  select role='admin' into actor_admin from public.profiles where id=p_actor_id;
  perform pg_advisory_xact_lock(hashtextextended(p_actor_id::text,2834));
  if not actor_admin and p_action<>'withdraw' and (select count(*) from public.community_exercise_audit where actor_id=p_actor_id and created_at>now()-interval '1 hour')>=30 then raise exception 'community quota'; end if;
  if p_action='draft' then
    if p_payload->>'exercise_id' is null then
      if (select count(*) from public.community_exercises where creator_id=p_actor_id)>=100 then raise exception 'community quota' using errcode='P0001'; end if;
      insert into public.community_exercises(creator_id) values(p_actor_id) returning * into e;
    else
      select * into e from public.community_exercises where id=(p_payload->>'exercise_id')::uuid for update;
      if e.id is null or e.creator_id is distinct from p_actor_id then raise exception 'community not found' using errcode='P0002'; end if;
      if (p_payload->>'expected_revision_id')::uuid is distinct from e.current_revision_id then raise exception 'community revision changed' using errcode='40001'; end if;
    end if;
    if p_payload->>'media_id' is not null then
      select * into m from public.private_exercise_media where id=(p_payload->>'media_id')::uuid and athlete_id=p_actor_id for share;
      if m.id is null then raise exception 'community media not owned' using errcode='42501'; end if;
      if m.provider='uploaded' then
        select * into a from public.private_video_assets where id=m.asset_id for share;
        if a.status<>'verified' then raise exception 'community media not verified'; end if;
      end if;
    end if;
    -- Identical retries do not manufacture revisions or reset decisions.
    select * into r from public.community_exercise_revisions where id=e.current_revision_id;
    if r.id is not null and r.name=btrim(p_payload->>'name') and r.equipment is not distinct from p_payload->>'equipment'
      and r.notes is not distinct from p_payload->>'notes' and r.media_id is not distinct from (p_payload->>'media_id')::uuid then return r.id; end if;
    if (select count(*) from public.community_exercise_audit where actor_id=p_actor_id and action='draft' and created_at>now()-interval '1 hour')>=30 then raise exception 'community quota'; end if;
    insert into public.community_exercise_revisions(exercise_id,name,equipment,notes,media_id)
      values(e.id,btrim(p_payload->>'name'),p_payload->>'equipment',p_payload->>'notes',(p_payload->>'media_id')::uuid) returning id into next_id;
    if r.status='in_review' then update public.community_exercise_revisions set status='superseded' where id=r.id; end if;
    update public.community_exercises set current_revision_id=next_id where id=e.id;
  else
    select * into r from public.community_exercise_revisions where id=(p_payload->>'revision_id')::uuid;
    select * into e from public.community_exercises where id=r.exercise_id for update;
    -- Re-read after the exercise lock; concurrent admin decisions cannot race.
    select * into r from public.community_exercise_revisions where id=(p_payload->>'revision_id')::uuid for update;
    if e.id is null then raise exception 'community not found' using errcode='P0002'; end if;
    next_id:=r.id;
    if p_action in ('edit','verify','confirm','approve','request_changes','reject','remove') then
      if not actor_admin then raise exception 'community forbidden' using errcode='42501'; end if;
      if p_action<>'remove' and e.current_revision_id<>r.id then raise exception 'community revision changed' using errcode='40001'; end if;
    elsif p_action in ('submit','withdraw') then
      if e.creator_id is distinct from p_actor_id then raise exception 'community forbidden' using errcode='42501'; end if;
      if p_action='submit' and e.current_revision_id<>r.id then raise exception 'community revision changed' using errcode='40001'; end if;
    elsif p_action<>'report' then raise exception 'invalid community action'; end if;
    if p_action='approve' and r.status='published' and e.published_revision_id=r.id and e.attribution_consent
      and coalesce((p_payload->>'final_confirmation')::boolean,false) then return r.id; end if;
    if p_action='withdraw' and not e.attribution_consent and e.published_revision_id is null then return e.current_revision_id; end if;
    if p_action='submit' then
      if not coalesce((p_payload->>'share_rights')::boolean,false) or not coalesce((p_payload->>'attribution_consent')::boolean,false)
        or not exists(select 1 from public.profiles where id=p_actor_id and username is not null) then raise exception 'community consent required'; end if;
      if r.status='in_review' then return r.id; end if;
      if r.media_id is not null then
        select * into m from public.private_exercise_media where id=r.media_id for share;
        if m.id is null then raise exception 'community media missing'; end if;
        if m.provider='uploaded' then select * into a from public.private_video_assets where id=m.asset_id for share; if a.status<>'verified' then raise exception 'community media not verified'; end if; end if;
      end if;
      if r.status not in ('private','changes_requested','rejected') then raise exception 'invalid review transition'; end if;
      if (select count(*) from public.community_exercise_audit where actor_id=p_actor_id and action='submit' and created_at>now()-interval '1 day')>=10 then raise exception 'community quota'; end if;
      update public.community_exercises set attribution_consent=true,consent_at=now(),withdrawn_at=null where id=e.id;
      update public.community_exercise_revisions set status='in_review',submitted_at=now(),verified_at=null,verified_by=null,verified_media_id=null,verified_proof=null,confirmed_at=null,confirmed_by=null,decision_reason=null where id=r.id;
    elsif p_action='withdraw' then
      update public.community_exercises set attribution_consent=false,published_revision_id=null,withdrawn_at=now() where id=e.id;
      update public.community_exercise_revisions set status='private',verified_at=null,confirmed_at=null where id=e.current_revision_id and status<>'published';
    elsif p_action='report' then
      if e.published_revision_id is distinct from r.id or not e.attribution_consent or e.creator_id is null then raise exception 'community not found' using errcode='P0002'; end if;
      if (select count(*) from public.community_exercise_reports where reporter_id=p_actor_id and created_at>now()-interval '1 day')>=5 then raise exception 'community quota'; end if;
      insert into public.community_exercise_reports(revision_id,reporter_id,reason) values(r.id,p_actor_id,btrim(p_payload->>'reason')) on conflict(revision_id,reporter_id) do nothing;
    elsif p_action='remove' then
      if nullif(btrim(p_payload->>'reason'),'') is null then raise exception 'decision reason required'; end if;
      update public.community_exercises set published_revision_id=null where id=e.id;
      update public.community_exercise_reports set status='resolved' where revision_id in(select id from public.community_exercise_revisions where exercise_id=e.id);
    else
      if r.status<>'in_review' and not(p_action='edit' and r.status='published') then raise exception 'invalid review transition'; end if;
      if p_action='edit' then
        if p_payload->>'media_id' is not null then
          select * into m from public.private_exercise_media where id=(p_payload->>'media_id')::uuid and athlete_id in(e.creator_id,p_actor_id) for share;
          if m.id is null then raise exception 'community media not owned' using errcode='42501'; end if;
          if m.provider='uploaded' then select * into a from public.private_video_assets where id=m.asset_id for share; if a.status<>'verified' then raise exception 'community media not verified'; end if; end if;
        end if;
        insert into public.community_exercise_revisions(exercise_id,name,equipment,notes,media_id,status,submitted_at)
          values(e.id,btrim(p_payload->>'name'),p_payload->>'equipment',p_payload->>'notes',(p_payload->>'media_id')::uuid,'in_review',r.submitted_at) returning id into next_id;
        update public.community_exercise_revisions set status='superseded' where id=r.id and status='in_review';
        update public.community_exercises set current_revision_id=next_id where id=e.id;
      elsif p_action='verify' then
        if (p_payload->>'verified_media_id')::uuid is distinct from r.media_id then raise exception 'community revision changed' using errcode='40001'; end if;
        if r.media_id is not null then
          select * into m from public.private_exercise_media where id=r.media_id for share;
          if m.id is null then raise exception 'community media missing'; end if;
          if m.provider='uploaded' then
            select * into a from public.private_video_assets where id=m.asset_id for share;
            if a.status<>'verified' or a.sha256 is distinct from p_payload->>'sha256' then raise exception 'community media not verified'; end if;
          else
            if p_payload->>'youtube_id' is distinct from m.video_id or not coalesce((p_payload->>'youtube_verified')::boolean,false) then raise exception 'community media not verified'; end if;
          end if;
        end if;
        proof:=jsonb_build_object('media_id',r.media_id,'sha256',a.sha256,'youtube_id',m.video_id);
        update public.community_exercise_revisions set verified_at=now(),verified_by=p_actor_id,verified_media_id=r.media_id,verified_proof=proof,confirmed_at=null,confirmed_by=null where id=r.id;
      elsif p_action='confirm' then
        if r.verified_at is null or r.verified_media_id is distinct from r.media_id or not coalesce((p_payload->>'final_confirmation')::boolean,false) then raise exception 'final revision must be verified and confirmed'; end if;
        update public.community_exercise_revisions set confirmed_at=now(),confirmed_by=p_actor_id where id=r.id;
      elsif p_action='approve' then
        if r.verified_at is null or r.verified_at<now()-interval '24 hours' or r.confirmed_at is null or r.verified_media_id is distinct from r.media_id
          or not coalesce((p_payload->>'final_confirmation')::boolean,false) then raise exception 'final revision must be verified and confirmed'; end if;
        if not e.attribution_consent or not exists(select 1 from public.profiles where id=e.creator_id and username is not null) then raise exception 'community consent required'; end if;
        if r.media_id is not null then
          select * into m from public.private_exercise_media where id=r.media_id for share;
          if m.id is null then raise exception 'community media missing'; end if;
          if m.provider='uploaded' then
            select * into a from public.private_video_assets where id=m.asset_id for share;
            if a.status<>'verified' or a.sha256 is distinct from r.verified_proof->>'sha256' then raise exception 'community media not verified'; end if;
          end if;
        end if;
        update public.community_exercise_revisions set status='published' where id=r.id;
        update public.community_exercises set published_revision_id=r.id where id=e.id;
      elsif p_action in ('reject','request_changes') then
        if nullif(btrim(p_payload->>'reason'),'') is null then raise exception 'decision reason required'; end if;
        update public.community_exercise_revisions set status=case when p_action='reject' then 'rejected' else 'changes_requested' end,
          decision_reason=btrim(p_payload->>'reason'),confirmed_at=null where id=r.id;
      end if;
    end if;
  end if;
  insert into public.community_exercise_audit(exercise_id,revision_id,actor_id,action,details)
    values(e.id,next_id,p_actor_id,p_action,jsonb_build_object('previous_revision_id',r.id,'reason',p_payload->>'reason','share_rights',p_payload->'share_rights',
      'attribution_consent',p_payload->'attribution_consent','before',case when p_action='edit' then to_jsonb(r) else null end,
      'after',case when p_action in('draft','edit') then public.community_revision_payload(next_id)-'raw_media'-'contributor' else null end));
  return next_id;
end $$;

revoke all on function public.community_revision_payload(uuid),public.community_detail(uuid,uuid,boolean),public.community_list(uuid,text,text,integer,integer),public.community_command(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.community_revision_payload(uuid),public.community_detail(uuid,uuid,boolean),public.community_list(uuid,text,text,integer,integer),public.community_command(uuid,text,jsonb) to service_role;

-- Retention must treat an active review/publication and saved community snapshot
-- as a durable reference. Stage A still owns all byte processing and deletion.
create function public.community_media_retained(p_media_id uuid) returns boolean
language sql security invoker set search_path='' as $$
  select exists(select 1 from public.community_exercise_revisions r join public.community_exercises e on e.id=r.exercise_id
    where r.media_id=p_media_id and ((e.current_revision_id=r.id and r.status='in_review')
      or (e.published_revision_id=r.id and e.attribution_consent and e.creator_id is not null)
      or exists(select 1 from public.custom_training_plans p cross join lateral jsonb_array_elements(p.sessions) s
        cross join lateral jsonb_array_elements(s->'exercises') x where x->>'community_revision_id'=r.id::text)));
$$;
revoke all on function public.community_media_retained(uuid) from public,anon,authenticated;
grant execute on function public.community_media_retained(uuid) to service_role;

create or replace function public.cleanup_private_youtube_previews(p_athlete_id uuid default null) returns integer
language plpgsql security invoker set search_path = '' as $$
declare candidate public.private_exercise_media; removed integer := 0;
begin
  for candidate in select m.* from public.private_exercise_media m
    where m.provider='youtube' and m.created_at < now() - interval '24 hours'
      and (p_athlete_id is null or m.athlete_id=p_athlete_id) and not public.community_media_retained(m.id)
      and not exists (select 1 from public.custom_training_plans p
        cross join lateral jsonb_array_elements(p.sessions) s
        cross join lateral jsonb_array_elements(s->'exercises') e
        where p.athlete_id=m.athlete_id and e->>'media_id'=m.id::text)
    order by m.created_at for update skip locked limit 200
  loop
    -- Lock matches the plan-save trigger. Recheck references after the lock so
    -- a concurrent save either retains the clip or fails without a dangling ID.
    if not public.community_media_retained(candidate.id) and not exists (select 1 from public.custom_training_plans p
      cross join lateral jsonb_array_elements(p.sessions) s
      cross join lateral jsonb_array_elements(s->'exercises') e
      where p.athlete_id=candidate.athlete_id and e->>'media_id'=candidate.id::text) then
      delete from public.private_exercise_media where id=candidate.id;
      removed := removed + 1;
    end if;
  end loop;
  return removed;
end $$;

create or replace function public.private_video_cleanup_candidates() returns setof public.private_video_assets
language plpgsql security invoker set search_path = '' as $$
declare candidate public.private_video_assets;
begin
  for candidate in select a.* from public.private_video_assets a where
      (a.status in ('reserved','queued','processing','rejected','deleted') and a.updated_at < now() - interval '24 hours')
      or (a.status='verified' and a.created_at < now() - interval '7 days')
      order by a.created_at for update skip locked limit 100
  loop
    -- Recheck references after acquiring the row lock shared with the plan trigger.
    if not exists (select 1 from public.private_exercise_media m where m.asset_id=candidate.id and public.community_media_retained(m.id)) and not exists (
        select 1 from public.private_exercise_media m join public.custom_training_plans p on p.athlete_id=m.athlete_id
        cross join lateral jsonb_array_elements(p.sessions) s
        cross join lateral jsonb_array_elements(s->'exercises') e
        where m.asset_id=candidate.id and e->>'media_id'=m.id::text) then
      update public.private_video_assets set status='deleted' where id=candidate.id;
      candidate.status := 'deleted';
      return next candidate;
    end if;
  end loop;
end;
$$;

create or replace function public.validate_custom_plan_private_media() returns trigger
language plpgsql security invoker set search_path = '' as $$
declare identity text; owned_id uuid; reference uuid; contribution public.community_exercises; revision public.community_exercise_revisions; media public.private_exercise_media; asset public.private_video_assets;
begin
  for identity in select e->>'media_id' from jsonb_array_elements(new.sessions) s
    cross join lateral jsonb_array_elements(s->'exercises') e where e->>'media_id' is not null
  loop
    select * into media from public.private_exercise_media where id=identity::uuid and athlete_id=new.athlete_id for share;
    if media.id is null then raise exception 'private media not owned'; end if;
    if media.provider='uploaded' then
      select * into asset from public.private_video_assets where id=media.asset_id and athlete_id=new.athlete_id for share;
      if asset.id is null or asset.status <> 'verified' then raise exception 'private media not verified'; end if;
    end if;
  end loop;
  for owned_id in select (x->>'community_id')::uuid from jsonb_array_elements(new.sessions) s
    cross join lateral jsonb_array_elements(s->'exercises') x where x->>'community_id' is not null
  loop
    if not exists(select 1 from public.community_exercises where id=owned_id and creator_id=new.athlete_id) then raise exception 'community exercise not owned'; end if;
  end loop;
  for reference in select (x->>'community_revision_id')::uuid from jsonb_array_elements(new.sessions) s
    cross join lateral jsonb_array_elements(s->'exercises') x where x->>'community_revision_id' is not null
  loop
    select * into revision from public.community_exercise_revisions where id=reference;
    select * into contribution from public.community_exercises where id=revision.exercise_id for share;
    if revision.id is null then raise exception 'community revision not found'; end if;
    if not coalesce((contribution.published_revision_id=reference and contribution.attribution_consent and contribution.creator_id is not null and public.community_revision_available(reference) and exists(select 1 from public.profiles where id=contribution.creator_id and username is not null)),false)
      and not (tg_op='UPDATE' and exists(select 1 from jsonb_array_elements(old.sessions) s
        cross join lateral jsonb_array_elements(s->'exercises') x where x->>'community_revision_id'=reference::text)) then
      raise exception 'community revision not published';
    end if;
  end loop;
  return new;
end $$;


create function public.community_owned_revision(p_actor_id uuid,p_exercise_id uuid) returns uuid
language plpgsql security invoker set search_path='' as $$
declare identity uuid;
begin
  select current_revision_id into identity from public.community_exercises where id=p_exercise_id and creator_id=p_actor_id;
  if identity is null then raise exception 'community not found' using errcode='P0002'; end if;
  return identity;
end $$;
revoke all on function public.community_owned_revision(uuid,uuid) from public,anon,authenticated;
grant execute on function public.community_owned_revision(uuid,uuid) to service_role;

create function public.community_creator_deleted() returns trigger
language plpgsql security invoker set search_path='' as $$
begin
  insert into public.community_exercise_audit(exercise_id,revision_id,action)
    select id,current_revision_id,'creator_deleted' from public.community_exercises where creator_id=old.id;
  update public.community_exercises set attribution_consent=false,published_revision_id=null,withdrawn_at=now() where creator_id=old.id;
  return old;
end $$;
revoke all on function public.community_creator_deleted() from public,anon,authenticated;
create trigger community_creator_deleted before delete on public.profiles for each row execute function public.community_creator_deleted();
