-- Keep pending decisions distinct from review history. Previous migrations are already applied.
create or replace function public.community_list(p_actor_id uuid,p_scope text,p_query text default '',p_offset integer default 0,p_limit integer default 30) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare ids uuid[]; total integer;
begin
  if not exists(select 1 from public.profiles where id=p_actor_id and access_status='approved') then raise exception 'community forbidden' using errcode='42501'; end if;
  if p_scope not in ('public','mine','review','history') then raise exception 'invalid community scope'; end if;
  if p_scope in ('review','history') and not exists(select 1 from public.profiles where id=p_actor_id and role='admin') then raise exception 'community forbidden' using errcode='42501'; end if;
  with candidates as (
    select r.id,r.created_at from public.community_exercises e
    join public.community_exercise_revisions r on r.id=case when p_scope='public' then e.published_revision_id else e.current_revision_id end
    left join public.profiles p on p.id=e.creator_id
    where (p_scope='mine' and e.creator_id=p_actor_id
      or p_scope='review' and (r.status='in_review' or exists(select 1 from public.community_exercise_reports x join public.community_exercise_revisions z on z.id=x.revision_id where z.exercise_id=e.id and x.status='open'))
      or p_scope='history' and (r.status in ('changes_requested','rejected','published') or (r.status='private' and r.submitted_at is not null))
        and not exists(select 1 from public.community_exercise_reports x join public.community_exercise_revisions z on z.id=x.revision_id where z.exercise_id=e.id and x.status='open')
      or p_scope='public' and e.attribution_consent and p.username is not null and public.community_revision_available(r.id))
      and (p_query='' or strpos(lower(r.name||' '||coalesce(r.equipment,'')),lower(left(p_query,100)))>0)
  ) select count(*)::integer, (select array_agg(id order by created_at desc,id) from (select * from candidates order by created_at desc,id offset greatest(p_offset,0) limit least(greatest(p_limit,1),50)) page)
    into total,ids from candidates;
  return jsonb_build_object('entries',(select coalesce(jsonb_agg(public.community_revision_payload(id) order by ord),'[]') from unnest(ids) with ordinality t(id,ord)),
    'total',total,'next_offset',case when greatest(p_offset,0)+least(greatest(p_limit,1),50)<total then greatest(p_offset,0)+least(greatest(p_limit,1),50) else null end);
end $$;
