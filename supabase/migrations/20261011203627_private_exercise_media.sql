-- PR A of #2833: private immutable demos; no publication or review privileges.
create table public.private_video_assets (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  status text not null default 'reserved' check (status in ('reserved','queued','processing','verified','rejected','deleted')),
  size_bytes integer not null check (size_bytes between 1 and 20971520),
  content_type text not null check (content_type in ('video/mp4','video/quicktime','video/webm')),
  intake_path text not null unique,
  rendition_path text unique,
  duration_seconds double precision check (duration_seconds > 0 and duration_seconds <= 30),
  width integer check (width between 16 and 1920),
  height integer check (height between 16 and 1920),
  sha256 text,
  processor_version text,
  upload_expires_at timestamptz not null default now() + interval '5 minutes',
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (status <> 'verified' or (rendition_path is not null and duration_seconds is not null
    and width is not null and height is not null and sha256 is not null and processor_version = 'isolated-v1')),
  unique (id, athlete_id)
);
create index private_video_assets_owner_created_idx on public.private_video_assets(athlete_id, created_at);
create trigger private_video_assets_updated before update on public.private_video_assets
  for each row execute function public.set_updated_at();

create table public.private_exercise_media (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  provider text not null check (provider in ('youtube','uploaded')),
  video_id text,
  asset_id uuid unique,
  start_s integer not null default 0 check (start_s >= 0),
  end_s integer not null check (end_s > start_s and end_s - start_s <= 30),
  channel_title text,
  orientation text check (orientation in ('portrait','landscape')),
  made_for_kids boolean,
  created_at timestamptz not null default now(),
  foreign key (asset_id, athlete_id) references public.private_video_assets(id, athlete_id) on delete cascade,
  check ((provider = 'youtube' and video_id ~ '^[A-Za-z0-9_-]{11}$' and asset_id is null and made_for_kids is not null)
    or (provider = 'uploaded' and video_id is null and asset_id is not null and start_s = 0))
);
create index private_exercise_media_owner_idx on public.private_exercise_media(athlete_id);
create table public.private_media_budget (
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  upload boolean not null,
  created_at timestamptz not null default now()
);
create index private_media_budget_owner_created_idx on public.private_media_budget(athlete_id, created_at);
create table public.private_media_worker_health (
  id text primary key check (id = 'isolated-v1'),
  healthy_at timestamptz not null
);
alter table public.private_video_assets enable row level security;
alter table public.private_exercise_media enable row level security;
alter table public.private_media_budget enable row level security;
alter table public.private_media_worker_health enable row level security;
revoke all on public.private_video_assets, public.private_exercise_media, public.private_media_budget,
  public.private_media_worker_health from anon, authenticated;
grant select on public.private_video_assets, public.private_exercise_media to authenticated;
grant all on public.private_video_assets, public.private_exercise_media, public.private_media_budget,
  public.private_media_worker_health to service_role;
create policy private_video_assets_owner on public.private_video_assets for select to authenticated
  using (athlete_id = (select auth.uid()));
create policy private_exercise_media_owner on public.private_exercise_media for select to authenticated
  using (athlete_id = (select auth.uid()));

-- All quota reservations serialize for an owner, including concurrent workers/API instances.
create function public.claim_private_media_budget(p_athlete_id uuid) returns boolean
language plpgsql security invoker set search_path = '' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 2833));
  delete from public.private_media_budget where athlete_id = p_athlete_id and created_at < now() - interval '1 day';
  if (select count(*) from public.private_media_budget where athlete_id = p_athlete_id and created_at > now() - interval '1 hour') >= 30
    or (select count(*) from public.private_exercise_media where athlete_id = p_athlete_id) >= 200 then
    return false;
  end if;
  insert into public.private_media_budget(athlete_id, upload) values (p_athlete_id, false);
  return true;
end $$;

create function public.reserve_private_video(p_athlete_id uuid, p_size_bytes integer, p_content_type text)
returns setof public.private_video_assets language plpgsql security invoker set search_path = '' as $$
declare asset_uuid uuid := gen_random_uuid();
begin
  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 2833));
  if not public.claim_private_media_budget(p_athlete_id) then return; end if;
  if (select count(*) from public.private_media_budget where athlete_id = p_athlete_id and upload and created_at > now() - interval '1 hour') >= 6
    or (select count(*) from public.private_media_budget where athlete_id = p_athlete_id and upload) >= 20
    or (select count(*) from public.private_video_assets where athlete_id = p_athlete_id and status not in ('deleted','rejected')) >= 50
    or (select coalesce(sum(size_bytes),0) from public.private_video_assets where athlete_id = p_athlete_id and status not in ('deleted','rejected')) + p_size_bytes > 1048576000 then
    return;
  end if;
  update public.private_media_budget set upload = true
    where ctid = (select ctid from public.private_media_budget where athlete_id = p_athlete_id order by created_at desc limit 1);
  return query insert into public.private_video_assets(id,athlete_id,size_bytes,content_type,intake_path)
    values (asset_uuid,p_athlete_id,p_size_bytes,p_content_type,p_athlete_id::text || '/' || asset_uuid::text || '/source') returning *;
end $$;
revoke all on function public.claim_private_media_budget(uuid), public.reserve_private_video(uuid,integer,text) from public,anon,authenticated;
grant execute on function public.claim_private_media_budget(uuid), public.reserve_private_video(uuid,integer,text) to service_role;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types) values
  ('private-demo-intake','private-demo-intake',false,20971520,array['video/mp4','video/quicktime','video/webm']),
  ('private-demo-ready','private-demo-ready',false,20971520,array['video/mp4'])
on conflict(id) do update set public=false,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;

-- Restrictive guards protect these buckets even if another feature has broad permissive policies.
create policy private_demo_no_client_read on storage.objects as restrictive for select to anon,authenticated
  using (bucket_id not in ('private-demo-intake','private-demo-ready'));
create policy private_demo_no_client_update on storage.objects as restrictive for update to anon,authenticated
  using (bucket_id not in ('private-demo-intake','private-demo-ready'))
  with check (bucket_id not in ('private-demo-intake','private-demo-ready'));
create policy private_demo_no_client_delete on storage.objects as restrictive for delete to anon,authenticated
  using (bucket_id not in ('private-demo-intake','private-demo-ready'));
create policy private_demo_intake_guard on storage.objects as restrictive for insert to anon,authenticated
  with check (bucket_id not in ('private-demo-intake','private-demo-ready') or
    (bucket_id = 'private-demo-intake' and exists (
      select 1 from public.private_video_assets a where a.intake_path = name
        and a.athlete_id = (select auth.uid()) and a.status = 'reserved' and a.upload_expires_at > now())));
create policy private_demo_intake_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'private-demo-intake' and exists (
    select 1 from public.private_video_assets a where a.intake_path = name
      and a.athlete_id = (select auth.uid()) and a.status = 'reserved' and a.upload_expires_at > now()));

-- Worker claims only complete objects, once. No client can manipulate processing state.
create function public.claim_private_video() returns setof public.private_video_assets
language plpgsql security invoker set search_path = '' as $$
declare claimed uuid;
begin
  select a.id into claimed from public.private_video_assets a
    where a.status = 'reserved' and exists (select 1 from storage.objects o where o.bucket_id = 'private-demo-intake' and o.name = a.intake_path)
    order by a.created_at for update of a skip locked limit 1;
  return query update public.private_video_assets set status='processing' where id=claimed returning *;
end $$;
create function public.finish_private_video(p_asset_id uuid, p_duration double precision, p_width integer, p_height integer, p_sha256 text)
returns void language plpgsql security invoker set search_path = '' as $$
declare asset public.private_video_assets;
begin
  update public.private_video_assets set status='verified',duration_seconds=p_duration,width=p_width,height=p_height,
    rendition_path=athlete_id::text || '/' || id::text || '/demo.mp4',sha256=p_sha256,processor_version='isolated-v1',processed_at=now()
    where id=p_asset_id and status='processing' returning * into asset;
  if asset.id is null then raise exception 'asset not processing'; end if;
  insert into public.private_exercise_media(athlete_id,provider,asset_id,start_s,end_s,orientation)
    values(asset.athlete_id,'uploaded',asset.id,0,ceil(p_duration)::integer,
      case when p_height > p_width then 'portrait' else 'landscape' end);
end $$;
revoke all on function public.claim_private_video(), public.finish_private_video(uuid,double precision,integer,integer,text) from public,anon,authenticated;
grant execute on function public.claim_private_video(), public.finish_private_video(uuid,double precision,integer,integer,text) to service_role;

-- Unused reservations/rejected/stalled jobs: remove within 24h. Orphan renditions: 7 days.
-- Saved JSON references are checked here, never trusted from cleanup request parameters.
create function public.private_video_cleanup_candidates() returns setof public.private_video_assets
language plpgsql security invoker set search_path = '' as $$
declare candidate public.private_video_assets;
begin
  for candidate in select a.* from public.private_video_assets a where
      (a.status in ('reserved','queued','processing','rejected','deleted') and a.created_at < now() - interval '24 hours')
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
revoke all on function public.private_video_cleanup_candidates() from public,anon,authenticated;
grant execute on function public.private_video_cleanup_candidates() to service_role;

-- Account deletion cascades database rows; the worker also removes dangling storage objects.
create function public.private_demo_orphan_objects() returns table(bucket_id text, name text)
language sql security invoker set search_path = '' as $$
  select o.bucket_id,o.name from storage.objects o
    where o.bucket_id in ('private-demo-intake','private-demo-ready') and o.created_at < now() - interval '1 hour'
      and not exists (select 1 from public.private_video_assets a
        where o.name=a.intake_path or o.name=a.athlete_id::text || '/' || a.id::text || '/demo.mp4')
    limit 100;
$$;
revoke all on function public.private_demo_orphan_objects() from public,anon,authenticated;
grant execute on function public.private_demo_orphan_objects() to service_role;

-- Defense in depth and cleanup/save serialization. A direct privileged JSON write
-- cannot attach another athlete's demo or resurrect an asset already being removed.
create function public.validate_custom_plan_private_media() returns trigger
language plpgsql security invoker set search_path = '' as $$
declare identity text; media public.private_exercise_media; asset public.private_video_assets;
begin
  for identity in select e->>'media_id' from jsonb_array_elements(new.sessions) s
    cross join lateral jsonb_array_elements(s->'exercises') e where e->>'media_id' is not null
  loop
    select * into media from public.private_exercise_media where id=identity::uuid and athlete_id=new.athlete_id;
    if media.id is null then raise exception 'private media not owned'; end if;
    if media.provider='uploaded' then
      select * into asset from public.private_video_assets where id=media.asset_id and athlete_id=new.athlete_id for share;
      if asset.id is null or asset.status <> 'verified' then raise exception 'private media not verified'; end if;
    end if;
  end loop;
  return new;
end $$;
revoke all on function public.validate_custom_plan_private_media() from public,anon,authenticated;
create trigger validate_custom_plan_private_media before insert or update of sessions on public.custom_training_plans
  for each row execute function public.validate_custom_plan_private_media();
