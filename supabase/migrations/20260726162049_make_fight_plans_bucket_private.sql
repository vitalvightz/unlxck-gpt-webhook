-- Keep legacy fight-plan PDFs stored, but prevent anonymous public downloads.
-- The current application does not depend on public PDF URLs.
update storage.buckets
set public = false
where id = 'fight-plans';
