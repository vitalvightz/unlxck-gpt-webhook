alter table public.generation_jobs
  alter column source set default 'self_serve';

update public.generation_jobs
  set source = 'self_serve'
  where source = 'self_service';
