-- Synthetic fixtures only; refuse hosted/default database names. Roll back all fixtures.
begin;
do $$ begin
 if current_database() not like 'analytics_%' then raise exception 'Disposable analytics_ database required'; end if;
end $$;
-- Mirror the production foreign keys when using the catalog-derived rehearsal.
do $$ begin
 if not exists(select 1 from pg_constraint where conrelid='public.session_completions'::regclass and contype='f' and confrelid='public.plans'::regclass) then
  alter table public.session_completions add foreign key(plan_id) references public.plans(id) on delete cascade;
 end if;
 if not exists(select 1 from pg_constraint where conrelid='public.today_checkins'::regclass and contype='f' and confrelid='public.profiles'::regclass) then
  alter table public.today_checkins add foreign key(athlete_id) references public.profiles(id) on delete cascade;
 end if;
end $$;
do $$ declare
 actor uuid:=gen_random_uuid(); named uuid:=gen_random_uuid(); unnamed uuid:=gen_random_uuid(); mature uuid:=gen_random_uuid(); immature uuid:=gen_random_uuid(); review uuid:=gen_random_uuid(); late uuid:=gen_random_uuid(); manual uuid:=gen_random_uuid(); r jsonb; n int;
begin
 insert into public.profiles(id,email,role,created_at,date_of_birth,full_name)
 values(actor,'fallback@example.test','athlete',now()-interval '40 days','1990-01-01','  '),
 (named,'named@example.test','athlete',now()-interval '40 days','1990-01-01','Example Athlete');
 insert into public.profiles(id,email,role,created_at,date_of_birth,full_name)
 values(unnamed,null,'athlete',now(),'1990-01-01',null);
 if not exists(select 1 from jsonb_array_elements(public.product_analytics_facts(array['admin@example.test'])->'athletes') p where p->>'id'=unnamed::text) then raise exception 'Missing email removed UUID-fallback athlete from population'; end if;
 insert into public.plans(id,athlete_id,created_at,status) values
 (mature,actor,now()-interval '7 days','ready'),
 (immature,actor,now()-interval '7 days'+interval '1 microsecond','publishable_with_flags'),
 (review,actor,now()-interval '8 days','review_required'),
 (late,actor,now()-interval '8 days','ready');
 insert into public.session_completions(id,athlete_id,plan_id,session_id,training_day,started_at,completed_at,status) values
 (gen_random_uuid(),actor,mature,'first',current_date,now()-interval '2 days',now()-interval '1 day','modified'),
 (gen_random_uuid(),actor,late,'late',current_date,null,now()-interval '1 day','done'); -- exactly day 7: excluded
 insert into public.external_training_sessions(id,athlete_id,created_at) values(manual,actor,now()-interval '1 day');
 insert into public.sparring_logs(id,athlete_id,created_at,external_session_id) values(gen_random_uuid(),actor,now(),manual);
 insert into public.sparring_logs(id,athlete_id,created_at,plan_id,session_id,training_day) values(gen_random_uuid(),actor,now(),mature,'first',current_date);
 insert into public.session_logs(id,athlete_id,created_at,completed) values(gen_random_uuid(),actor,now()-interval '3 days',true);
 r=public.product_analytics_facts('{}',actor);
 if r#>>'{athletes,0,email}'<>'fallback@example.test' or r#>>'{athletes,0,full_name}'<>'  ' then raise exception 'Admin identity projection missing'; end if;
 if jsonb_array_length(r->'optional_coverage')<>0 then raise exception 'Invented consent coverage'; end if;
 if exists(select 1 from jsonb_array_elements(r->'facts') f where f->>'feature'='history') then raise exception 'Training counted as History visit'; end if;
 if jsonb_array_length(r->'training_records')<>3 then raise exception 'Linked sparring double counted or legacy identity guessed'; end if;
 if not (select (p->>'completed_within_7d')::boolean from jsonb_array_elements(r->'plans_used') p where p->>'id'=mature::text) then raise exception 'Valid seven-day completion missing'; end if;
 if (select (p->>'completed_within_7d')::boolean from jsonb_array_elements(r->'plans_used') p where p->>'id'=late::text) then raise exception 'Day-seven exclusive boundary counted'; end if;
 if exists(select 1 from jsonb_array_elements(r->'plans_used') p where p->>'opened_at' is not null) then raise exception 'Unobserved opening invented'; end if;
 if public.ingest_product_event(actor,'timer_started','timer',gen_random_uuid(),null) then raise exception 'Consent bypass'; end if;
 perform public.set_product_analytics_preference(actor,true);
 perform cron.alter_job((select jobid from cron.job where jobname='product-events-retention'),active:=false);
 if jsonb_array_length(public.product_analytics_facts('{}',actor)->'optional_coverage')<>0 then raise exception 'Unhealthy collection called measurable'; end if;
 perform cron.alter_job((select jobid from cron.job where jobname='product-events-retention'),active:=true);
 perform public.ingest_product_event(actor,'history_opened','history','00000000-0000-0000-0000-000000001234',null);
 perform public.ingest_product_event(actor,'history_opened','history','00000000-0000-0000-0000-000000001234',null);
 if (select count(*) from public.product_events where athlete_id=actor)<>1 then raise exception 'Refresh/retry not deduplicated'; end if;
 perform public.set_product_analytics_preference(actor,false);
 if public.ingest_product_event(actor,'timer_started','timer',gen_random_uuid(),null) then raise exception 'Withdrawal bypass'; end if;
 update public.profiles set analytics_excluded=true where id=actor;
 if public.set_product_analytics_preference(actor,true) then raise exception 'Excluded actor opted in'; end if;
 update public.profiles set analytics_excluded=false where id=actor;
 insert into public.product_events(athlete_id,event_name,feature,request_id,created_at)
 values(actor,'operation_failed','manual',gen_random_uuid(),now()-interval '8 days');
 r=public.product_analytics_facts('{}',actor);
 if not (r#>>'{error_returns,0,returned}')::boolean then raise exception 'Exact error return lost'; end if;
 delete from public.plans where id=mature;
 if exists(select 1 from public.session_completions where plan_id=mature) then raise exception 'Plan cascade changed'; end if;
 r=public.product_analytics_facts('{}',actor);
 if exists(select 1 from jsonb_array_elements(r->'plans_used') p where p->>'id'=mature::text) then raise exception 'Deleted plan retained'; end if;
 insert into public.today_checkins(id,athlete_id,created_at) values(gen_random_uuid(),named,now());
 delete from public.profiles where id=named;
 if exists(select 1 from public.today_checkins where athlete_id=named) then raise exception 'Account deletion changed'; end if;
 if jsonb_array_length(public.product_analytics_facts('{}',named)->'athletes')<>0 then raise exception 'Deleted identity retained'; end if;
 if has_function_privilege('authenticated','public.product_analytics_facts(text[],uuid)','execute')
 or has_table_privilege('authenticated','public.product_activity','select') then raise exception 'Admin identity or activity exposed'; end if;
end $$;
rollback;
