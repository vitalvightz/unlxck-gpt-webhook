-- Demo videos for plan exercises (api/services/exercise_media.py).
--
-- One row per exercise, keyed by a normalized slug of its name. The plan read
-- (GET /api/plans/*) resolves each block's display_name against exercise_key
-- or aliases at read time, so a video can be added, swapped or retired without
-- regenerating any plan. Video IDs are curated here and never produced by the
-- model.
--
-- Only rows with status = 'ok' are served. tools/exercise_media.py validates a
-- video through YouTube oEmbed before import, and the worker re-checks every
-- row daily: a deleted, private or embed-disabled video flips to 'unavailable'
-- and the athlete sees the cues-only row instead of a broken player.
--
-- Backend-only: the service role reads and writes. No anon/authenticated grant.
create table if not exists public.exercise_media (
  exercise_key text primary key
    check (char_length(exercise_key) between 1 and 120 and exercise_key ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  -- Extra normalized slugs that should resolve to this row (plan names drift:
  -- "Romanian Deadlift (RDL)" and "RDL" both land on romanian-deadlift).
  aliases text[] not null default '{}',
  provider text not null default 'youtube' check (provider in ('youtube')),
  video_id text not null check (video_id ~ '^[A-Za-z0-9_-]{11}$'),
  -- The segment the row loops: the rep that shows the movement, not the intro.
  start_s integer not null default 0 check (start_s >= 0),
  end_s integer check (end_s is null or end_s > start_s),
  -- 'coach' = filmed by the UNLXCK coaching team (renders a "Coach demo"
  -- badge); 'curated' = a vetted third-party demo.
  source text not null default 'curated' check (source in ('curated', 'coach')),
  status text not null default 'unverified' check (status in ('unverified', 'ok', 'unavailable')),
  status_reason text check (status_reason is null or char_length(status_reason) <= 200),
  verified_at timestamptz,
  notes text not null default '' check (char_length(notes) <= 500),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists exercise_media_aliases_idx
  on public.exercise_media using gin (aliases);

alter table public.exercise_media enable row level security;

revoke all on public.exercise_media from anon, authenticated;
