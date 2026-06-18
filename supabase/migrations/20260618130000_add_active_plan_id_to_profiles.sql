alter table public.profiles
add column if not exists active_plan_id uuid references public.plans(id) on delete set null;

create index if not exists profiles_active_plan_id_idx
on public.profiles(active_plan_id);
