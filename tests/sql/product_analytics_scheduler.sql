-- DESTRUCTIVE FIXTURES: disposable rehearsal database only, never production.
do $$ begin
 if current_database()<>'analytics_live_rehearsal' then raise exception 'Use the disposable analytics_live_rehearsal database only'; end if;
end $$;
insert into public.profiles(id,email,role,created_at,date_of_birth)
 values('00000000-0000-0000-0000-000000000099','expiry-rehearsal@example.test','athlete',now(),'1990-01-01');
insert into public.product_events(athlete_id,event_name,feature,request_id,created_at) values
 ('00000000-0000-0000-0000-000000000099','timer_started','timer','00000000-0000-0000-0000-000000000098',now()-interval '181 days'),
 ('00000000-0000-0000-0000-000000000099','timer_started','timer','00000000-0000-0000-0000-000000000097',now()-interval '179 days');
-- Exercise the actual scheduler/worker, not a direct call to the prune function.
select cron.schedule('product-events-retention','1 second','select public.prune_product_events()');
do $$ declare complete boolean:=false; begin
 for i in 1..50 loop
  if not exists(select 1 from public.product_events where request_id='00000000-0000-0000-0000-000000000098') then complete:=true; exit; end if;
  perform pg_sleep(0.2);
 end loop;
 if not complete then raise exception 'Scheduled retention did not remove expired event'; end if;
 if not exists(select 1 from public.product_events where request_id='00000000-0000-0000-0000-000000000097') then raise exception 'Scheduled retention removed event younger than 180 days'; end if;
end $$;
select cron.schedule('product-events-retention','17 3 * * *','select public.prune_product_events()');
select public.product_analytics_retention_health();
do $$ begin
 if not coalesce((public.product_analytics_retention_health()->>'healthy')::boolean,false)
 or public.product_analytics_retention_health()->>'last_success_at' is null then
  raise exception 'No successful scheduler run recorded';
 end if;
end $$;
-- Simulate overdue successes transactionally; keep genuine run history intact.
begin;
select public.set_product_analytics_preference('00000000-0000-0000-0000-000000000099',true);
update cron.job_run_details set end_time=now()-interval '37 hours'
 where jobid in(select jobid from cron.job where jobname='product-events-retention') and status='succeeded';
do $$ begin
 if coalesce((public.product_analytics_retention_health()->>'healthy')::boolean,true) then raise exception 'Overdue cleanup reported healthy'; end if;
 if public.ingest_product_event('00000000-0000-0000-0000-000000000099','timer_started','timer',gen_random_uuid(),null) then raise exception 'Overdue cleanup allowed collection'; end if;
end $$;
rollback;
delete from public.profiles where id='00000000-0000-0000-0000-000000000099';
