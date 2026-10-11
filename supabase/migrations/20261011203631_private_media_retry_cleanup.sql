-- Idempotent finalisation and bounded retention for abandoned private previews.
create or replace function public.claim_private_video() returns setof public.private_video_assets
language plpgsql security invoker set search_path = '' as $$
declare claimed uuid;
begin
  select a.id into claimed from public.private_video_assets a
    where (a.status = 'reserved' or (a.status = 'processing' and a.updated_at < now() - interval '10 minutes'))
      and exists (select 1 from storage.objects o where o.bucket_id='private-demo-intake' and o.name=a.intake_path)
    order by a.created_at for update of a skip locked limit 1;
  return query update public.private_video_assets set status='processing' where id=claimed returning *;
end $$;

create or replace function public.finish_private_video(p_asset_id uuid, p_duration double precision, p_width integer, p_height integer, p_sha256 text)
returns void language plpgsql security invoker set search_path = '' as $$
declare asset public.private_video_assets;
begin
  select * into asset from public.private_video_assets where id=p_asset_id for update;
  if asset.status='verified' then
    if asset.duration_seconds is distinct from p_duration or asset.width is distinct from p_width
      or asset.height is distinct from p_height or asset.sha256 is distinct from p_sha256 then
      raise exception 'finalisation revision mismatch';
    end if;
    return;
  end if;
  if asset.id is null or asset.status <> 'processing' then raise exception 'asset not processing'; end if;
  update public.private_video_assets set status='verified',duration_seconds=p_duration,width=p_width,height=p_height,
    rendition_path=athlete_id::text || '/' || id::text || '/demo.mp4',sha256=p_sha256,processor_version='isolated-v1',processed_at=now()
    where id=p_asset_id;
  insert into public.private_exercise_media(athlete_id,provider,asset_id,start_s,end_s,orientation)
    values(asset.athlete_id,'uploaded',asset.id,0,ceil(p_duration)::integer,
      case when p_height > p_width then 'portrait' else 'landscape' end);
end $$;

create function public.cleanup_private_youtube_previews(p_athlete_id uuid default null) returns integer
language plpgsql security invoker set search_path = '' as $$
declare candidate public.private_exercise_media; removed integer := 0;
begin
  for candidate in select m.* from public.private_exercise_media m
    where m.provider='youtube' and m.created_at < now() - interval '24 hours'
      and (p_athlete_id is null or m.athlete_id=p_athlete_id)
      and not exists (select 1 from public.custom_training_plans p
        cross join lateral jsonb_array_elements(p.sessions) s
        cross join lateral jsonb_array_elements(s->'exercises') e
        where p.athlete_id=m.athlete_id and e->>'media_id'=m.id::text)
    order by m.created_at for update skip locked limit 200
  loop
    -- Lock matches the plan-save trigger. Recheck references after the lock so
    -- a concurrent save either retains the clip or fails without a dangling ID.
    if not exists (select 1 from public.custom_training_plans p
      cross join lateral jsonb_array_elements(p.sessions) s
      cross join lateral jsonb_array_elements(s->'exercises') e
      where p.athlete_id=candidate.athlete_id and e->>'media_id'=candidate.id::text) then
      delete from public.private_exercise_media where id=candidate.id;
      removed := removed + 1;
    end if;
  end loop;
  return removed;
end $$;
revoke all on function public.cleanup_private_youtube_previews(uuid) from public,anon,authenticated;
grant execute on function public.cleanup_private_youtube_previews(uuid) to service_role;

create or replace function public.claim_private_media_budget(p_athlete_id uuid) returns boolean
language plpgsql security invoker set search_path = '' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 2833));
  perform public.cleanup_private_youtube_previews(p_athlete_id);
  delete from public.private_media_budget where athlete_id=p_athlete_id and created_at < now()-interval '1 day';
  if (select count(*) from public.private_media_budget where athlete_id=p_athlete_id and created_at > now()-interval '1 hour') >= 30
    or (select count(*) from public.private_exercise_media where athlete_id=p_athlete_id) >= 200 then
    return false;
  end if;
  insert into public.private_media_budget(athlete_id,upload) values(p_athlete_id,false);
  return true;
end $$;

create or replace function public.validate_custom_plan_private_media() returns trigger
language plpgsql security invoker set search_path = '' as $$
declare identity text; media public.private_exercise_media; asset public.private_video_assets;
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
  return new;
end $$;

-- Raw deletion can lose its response too. Verified raw objects are safe to
-- remove later; the ready object is retained for every saved attachment.
create or replace function public.private_demo_orphan_objects() returns table(bucket_id text, name text)
language sql security invoker set search_path = '' as $$
  select o.bucket_id,o.name from storage.objects o
    where o.bucket_id in ('private-demo-intake','private-demo-ready') and o.created_at < now()-interval '1 hour'
      and (not exists (select 1 from public.private_video_assets a
        where o.name=a.intake_path or o.name=a.athlete_id::text || '/' || a.id::text || '/demo.mp4')
      or (o.bucket_id='private-demo-intake' and exists (select 1 from public.private_video_assets a
        where a.intake_path=o.name and a.status='verified')))
    limit 100;
$$;

-- Active retry leases must expire before stalled-job retention.
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
    if not exists (
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
