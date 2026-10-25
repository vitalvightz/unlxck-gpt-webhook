-- Refuse production execution, even if someone pastes the wrong fixture file.
do $$ begin
 if current_database() not like 'analytics_%' then raise exception 'Use a disposable analytics_ rehearsal database only'; end if;
end $$;
-- Disposable database only. Bootstrap uses the exact analytics projection
-- columns of the existing application tables; no production data is touched.
insert into public.profiles(id,email,role,created_at,starting_path) values
 ('00000000-0000-0000-0000-000000000001','athlete@example.com','athlete',now()-interval '10 days','tracking_first'),
 ('00000000-0000-0000-0000-000000000002','admin@example.com','admin',now(),'plan_first'),
 ('00000000-0000-0000-0000-000000000003','internal@example.com','athlete',now(),'tracking_first'),
 ('00000000-0000-0000-0000-000000000004','allowlisted@example.com','athlete',now(),'plan_first');
insert into public.profiles(id,email,role,created_at,starting_path)
 values('00000000-0000-0000-0000-000000000005',' VITALVIGHTZ@GMAIL.COM ','athlete',now(),'tracking_first');
update public.profiles set date_of_birth='1990-01-01';
update public.profiles set analytics_excluded=true where email='internal@example.com';
do $$ begin
 if public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),null) then raise exception 'Consent bypass'; end if;
end $$;
select public.set_product_analytics_preference('00000000-0000-0000-0000-000000000001',true);
select public.set_product_analytics_preference('00000000-0000-0000-0000-000000000005',true);
do $$ begin
 if public.ingest_product_event('00000000-0000-0000-0000-000000000005','timer_started','timer',gen_random_uuid(),null) then raise exception 'Internal account collected'; end if;
 if has_table_privilege('authenticated','public.product_analytics_excluded_emails','SELECT') then raise exception 'Internal email registry exposed'; end if;
end $$;

select public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer','00000000-0000-0000-0000-000000000010',null);
select public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer','00000000-0000-0000-0000-000000000010',null);
select public.ingest_product_event('00000000-0000-0000-0000-000000000001','plan_opened','plans',gen_random_uuid(),null);
select public.ingest_product_event('00000000-0000-0000-0000-000000000001','plan_opened','plans',gen_random_uuid(),null);
do $$ declare job_id bigint; begin
 if (select consent_version from public.product_analytics_preferences where athlete_id='00000000-0000-0000-0000-000000000001')<>'product-analytics-v1' then raise exception 'Consent version missing'; end if;
 update public.profiles set date_of_birth=current_date-interval '16 years' where id='00000000-0000-0000-0000-000000000001';
 if public.set_product_analytics_preference('00000000-0000-0000-0000-000000000001',true) then raise exception 'Minor opt-in accepted'; end if;
 if public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),null) then raise exception 'Minor ingestion accepted'; end if;
 update public.profiles set date_of_birth='1990-01-01' where id='00000000-0000-0000-0000-000000000001';
 select jobid into job_id from cron.job where jobname='product-events-retention';
 perform cron.alter_job(job_id,active:=false);
 if public.set_product_analytics_preference('00000000-0000-0000-0000-000000000001',true) then raise exception 'Opt-in without expiry accepted'; end if;
 if public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),null) then raise exception 'Ingestion without expiry accepted'; end if;
 perform cron.alter_job(job_id,active:=true);
 if has_function_privilege('authenticated','public.product_analytics_retention_health()','EXECUTE') or has_function_privilege('authenticated','public.set_product_analytics_preference(uuid,boolean)','EXECUTE') then raise exception 'Consent/catalog RPC exposed'; end if;
end $$;
insert into public.plans(id,athlete_id,created_at,status) values(gen_random_uuid(),'00000000-0000-0000-0000-000000000001',now(),'ready');
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
-- Account deletion/recreation cannot delete the independent exclusion.
delete from public.profiles where id='00000000-0000-0000-0000-000000000005';
insert into public.profiles(id,email,role,created_at,date_of_birth)
 values('00000000-0000-0000-0000-000000000006','vitalvightz@gmail.com','athlete',now(),'1990-01-01');
do $$ begin
 if jsonb_array_length(public.product_analytics_facts(array['allowlisted@example.com'])->'athletes')<>1 then raise exception 'Recreated internal account included'; end if;
 if (select count(*) from public.product_analytics_excluded_emails)<>7 then raise exception 'Durable exclusion registry changed during account deletion'; end if;
end $$;
insert into public.product_events(athlete_id,event_name,feature,request_id,created_at)
 values('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),now()-interval '181 days');
select public.prune_product_events();
do $$ begin
 if (select count(*) from public.product_events)<>2 then raise exception 'Retention failed'; end if;
end $$;
select public.set_product_analytics_preference('00000000-0000-0000-0000-000000000001',false);
do $$ begin
 if public.ingest_product_event('00000000-0000-0000-0000-000000000001','timer_started','timer',gen_random_uuid(),null) then raise exception 'Withdrawal bypass'; end if;
end $$;
-- Legacy table-level UPDATE grants must not bypass the server-owned fields.
grant update on public.profiles to authenticated;
select set_config('request.jwt.claim.role','authenticated',false);
do $$ begin
 begin
  insert into public.profiles(id,email,role,created_at,starting_path)
 values('00000000-0000-0000-0000-000000000005',' VITALVIGHTZ@GMAIL.COM ','athlete',now(),'tracking_first');
update public.profiles set date_of_birth='1990-01-01';
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
