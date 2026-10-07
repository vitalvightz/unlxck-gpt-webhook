-- Immutable identity for unanswered injury-specific rehab response opportunities.
-- NULL means this completion has not been evaluated by the PR4.1 capture path;
-- an empty array means it was evaluated and raised no attributable prompts.
alter table public.session_completions
  add column if not exists rehab_response_contexts jsonb
    check (
      rehab_response_contexts is null
      or jsonb_typeof(rehab_response_contexts) = 'array'
    );

comment on column public.session_completions.rehab_response_contexts is
  'Server-owned immutable rehab response identities. Pending state is derived from canonical rehab_exposures, never a client-controlled answered flag.';

-- No policy or grant changes are needed: this column inherits the parent
-- completion row's owner-only SELECT policy, authenticated read-only grant,
-- anon denial, and service-role mutation boundary.
