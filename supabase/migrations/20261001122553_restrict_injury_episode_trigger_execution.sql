-- Internal trigger execution must not be exposed as a client-callable RPC.
-- Existing triggers continue invoking their owner-defined function.
revoke execute on function public.capture_injury_episode_change()
  from public, anon, authenticated;
