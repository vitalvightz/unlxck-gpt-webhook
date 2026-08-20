-- Training consistency and prescribed-plan adherence are different products.
-- Keep the existing adherence columns intact and add explicit athlete-facing
-- Training Streak state, rebuilt by the server from authoritative history.
alter table public.athlete_streaks
  add column if not exists training_current integer not null default 0
    check (training_current >= 0),
  add column if not exists training_best integer not null default 0
    check (training_best >= training_current),
  add column if not exists training_last_qualifying_day date;
