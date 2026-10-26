-- Read-only aggregate snapshots. Never export query text, parameters or rows.
SELECT stats_reset, dealloc FROM extensions.pg_stat_statements_info;
SELECT CASE WHEN query ILIKE '%profiles%' THEN 'profiles' ELSE 'plans' END AS category,
       queryid::text AS statement_id, calls,
       round(total_exec_time::numeric,2) AS total_exec_ms,
       round(mean_exec_time::numeric,2) AS mean_exec_ms, rows,
       (query ILIKE '%.*%') AS wildcard_projection,
       (query ILIKE '%athlete_id%') AS owner_scoped
FROM extensions.pg_stat_statements
WHERE query ~* '^\s*(select|with)'
  AND (query ILIKE '%public%profiles%' OR query ILIKE '%public%plans%')
ORDER BY total_exec_time DESC LIMIT 15;
-- Repeat the statement snapshot with ORDER BY calls DESC for frequency ranking.
WITH sample AS (SELECT p FROM public.plans p ORDER BY id LIMIT 50), sizes AS (
    SELECT octet_length(row_to_json(p)::text) AS full_bytes,
           octet_length(COALESCE((p).planning_brief::text,'')) AS planning_brief_bytes,
           octet_length(COALESCE((p).stage2_payload::text,'')) AS stage2_payload_bytes
    FROM sample
)
SELECT count(*) AS sample_rows, round(avg(full_bytes)) AS mean_full_bytes,
       max(full_bytes) AS max_full_bytes,
       round(avg(planning_brief_bytes)) AS mean_planning_brief_bytes,
       round(avg(stage2_payload_bytes)) AS mean_stage2_payload_bytes FROM sizes;
