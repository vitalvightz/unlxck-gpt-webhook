-- Disposable database only. Bootstrap uses the exact analytics projection
-- columns of the existing application tables; no production data is touched.
insert into public.profiles(id,email,role,created_at,starting_path) values
 ('00000000-0000-0000-0000-000000000001','athlete@example.com','athlete',now()-interval '10 days','tracking_first'),
 ('00000000-0000-0000-0000-000000000002','admin@example.com','admin',now(),'plan_first'),
 ('00000000-0000-0000-0000-000000000003','internal@example.com','athlete',now(),'tracking_first'),
 ('00000000-0000-0000-0000-000000000004','allowlisted@example.com','athlete',now(),'plan_first');
update public.profiles set analytics_excluded=true where email='internal@example.com';
do $$ begin
 if public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),null) then raise exception 'Consent bypass'; end if;
end $$;
insert into public.product_analytics_preferences values('00000000-0000-0000-0000-000000000001',true,now());
select public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer','00000000-0000-0000-0000-000000000010',null);
select public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer','00000000-0000-0000-0000-000000000010',null);
select public.ingest_product_event('00000000-0000-0000-0000-000000000001','plan_opened','plans',gen_random_uuid(),null);
select public.ingest_product_event('00000000-0000-0000-0000-000000000001','plan_opened','plans',gen_random_uuid(),null);
insert into public.plans values(gen_random_uuid(),'00000000-0000-0000-0000-000000000001',now(),'ready');
do $$ declare result jsonb; begin
 if (select count(*) from public.product_events)<>2 then raise exception 'Retry/discovery deduplication failed'; end if;
 if (select count(*) from public.product_activity where meaningful)<>1 then raise exception 'Generation/view counted as activity'; end if;
 result=public.product_analytics_facts(array['allowlisted@example.com']);
 if jsonb_array_length(result->'athletes')<>1 then raise exception 'Admin/internal exclusion failed'; end if;
 if has_table_privilege('authenticated','public.product_events','SELECT') or has_table_privilege('authenticated','public.product_events','INSERT') then raise exception 'Cross-athlete table access'; end if;
 if has_function_privilege('authenticated','public.product_analytics_facts(text[],uuid)','EXECUTE') then raise exception 'Report RPC exposed'; end if;
 if has_function_privilege('authenticated','public.ingest_product_event(uuid,text,text,uuid,uuid)','EXECUTE') then raise exception 'Actor spoofing RPC exposed'; end if;
end $$;
do $$ begin
 for i in 1..118 loop
  perform public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),null);
 end loop;
 if public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),null) then raise exception 'Per-minute cap failed'; end if;
 delete from public.product_events where event_name='timer_started' and request_id<>'00000000-0000-0000-0000-000000000010';
end $$;
insert into public.product_events(athlete_id,event_name,feature,request_id,created_at)
 values('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),now()-interval '181 days');
select public.prune_product_events();
do $$ begin
 if (select count(*) from public.product_events)<>2 then raise exception 'Retention failed'; end if;
end $$;
update public.product_analytics_preferences set enabled=false;
do $$ begin
 if public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),null) then raise exception 'Withdrawal bypass'; end if;
end $$;
-- Legacy table-level UPDATE grants must not bypass the server-owned fields.
grant update on public.profiles to authenticated;
select set_config('request.jwt.claim.role','authenticated',false);
do $$ begin
 begin
  update public.profiles set analytics_excluded=true where email='athlete@example.com';
  raise exception 'Client exclusion spoof accepted';
 exception when insufficient_privilege then null; end;
 begin
  update public.profiles set onboarding_completed_at=now() where email='athlete@example.com';
  raise exception 'Client onboarding spoof accepted';
 exception when insufficient_privilege then null; end;
end $$;
select set_config('request.jwt.claim.role','service_role',false);
select public.record_onboarding_stage('00000000-0000-0000-0000-000000000001',true);
do $$ begin
 if not exists(select 1 from public.profiles where email='athlete@example.com' and onboarding_started_at is not null and onboarding_completed_at is not null) then raise exception 'Workflow timestamp capture failed'; end if;
end $$;
-- Real empty-dataset reports/screenshots use a clean database after verification.
truncate public.product_events,public.product_analytics_preferences,public.plans,public.profiles cascade;
