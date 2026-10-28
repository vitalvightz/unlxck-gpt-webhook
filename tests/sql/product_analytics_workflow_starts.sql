-- Synthetic fixtures only; refuse hosted/default database names. Roll back all fixtures.
-- Requires the analytics migrations and a healthy product-events-retention job.
begin;
do $$ begin
 if current_database() not like 'analytics_%' then raise exception 'Disposable analytics_ database required'; end if;
 if not coalesce((public.product_analytics_retention_health()->>'healthy')::boolean,false) then
  raise exception 'Retention job must be healthy before ingestion can be tested';
 end if;
end $$;
do $$ declare
 adult uuid:=gen_random_uuid(); declined uuid:=gen_random_uuid(); withdrawn uuid:=gen_random_uuid();
 flagged uuid:=gen_random_uuid(); internal uuid:=gen_random_uuid(); minor uuid:=gen_random_uuid(); n int;
begin
 insert into public.profiles(id,email,role,created_at,date_of_birth) values
 (adult,'starts-adult@example.test','athlete',now()-interval '3 days','1990-01-01'),
 (declined,'starts-declined@example.test','athlete',now(),'1990-01-01'),
 (withdrawn,'starts-withdrawn@example.test','athlete',now(),'1990-01-01'),
 (flagged,'starts-flagged@example.test','athlete',now(),'1990-01-01'),
 (internal,' VitalVightz@Gmail.com ','athlete',now(),'1990-01-01'),
 (minor,'starts-minor@example.test','athlete',now(),(now()-interval '15 years')::date);
 update public.profiles set analytics_excluded=true where id=flagged;
 assert public.set_product_analytics_preference(adult,true);
 assert public.set_product_analytics_preference(withdrawn,true);
 assert not public.set_product_analytics_preference(withdrawn,false);
 assert not public.set_product_analytics_preference(flagged,true), 'excluded profile cannot opt in';
 assert not public.set_product_analytics_preference(internal,true), 'registry email cannot opt in';
 assert not public.set_product_analytics_preference(minor,true), 'minor cannot opt in';
 -- Excluded accounts stay excluded even with a stale stored opt-in.
 insert into public.product_analytics_preferences(athlete_id,enabled) values(flagged,true),(internal,true);

 -- Consented adult: both starts accepted; repeats on the same UTC day collapse to one row.
 assert public.ingest_product_event(adult,'checkin_started','recovery',gen_random_uuid());
 assert public.ingest_product_event(adult,'checkin_started','recovery',gen_random_uuid());
 assert public.ingest_product_event(adult,'sparring_log_started','sparring',gen_random_uuid());
 assert public.ingest_product_event(adult,'sparring_log_started','sparring',gen_random_uuid());
 select count(*) into n from public.product_events where athlete_id=adult;
 assert n=2, format('expected one row per start event per day, got %s', n);

 -- Declined, withdrawn, excluded, registry and minor accounts store nothing.
 assert not public.ingest_product_event(declined,'checkin_started','recovery',gen_random_uuid());
 assert not public.ingest_product_event(withdrawn,'checkin_started','recovery',gen_random_uuid());
 assert not public.ingest_product_event(flagged,'checkin_started','recovery',gen_random_uuid());
 assert not public.ingest_product_event(internal,'sparring_log_started','sparring',gen_random_uuid());
 assert not public.ingest_product_event(minor,'checkin_started','recovery',gen_random_uuid());
 select count(*) into n from public.product_events where athlete_id in (declined,withdrawn,flagged,internal,minor);
 assert n=0, 'no consent or excluded account must store events';

 -- Starts are never meaningful activity; only the saved record is.
 select count(*) into n from public.product_activity where athlete_id=adult and meaningful;
 assert n=0, 'a start alone must not activate an athlete';
 insert into public.today_checkins(id,athlete_id,created_at) values(gen_random_uuid(),adult,now());
 select count(*) into n from public.product_activity where athlete_id=adult and meaningful;
 assert n=1;

 -- Unknown event names remain rejected by the table constraint.
 begin
  perform public.ingest_product_event(adult,'checkin_answers','recovery',gen_random_uuid());
  raise exception 'uncontrolled event accepted';
 exception when check_violation then null;
 end;
end $$;
rollback;
