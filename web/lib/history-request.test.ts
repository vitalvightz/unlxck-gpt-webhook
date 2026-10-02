import assert from "node:assert/strict";
import test from "node:test";
import type { Session } from "@supabase/supabase-js";

import { ApiError } from "./api";
import { loadHistoryWithAuthRecovery } from "./history-request";
import { getSupabaseBrowserClient } from "./supabase";

test("History recovers stale authentication once and keeps account boundaries", async (t) => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = "https://history-test.supabase.co";
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = "test-anon-key";
  const auth = getSupabaseBrowserClient().auth;
  const originalGetSession = auth.getSession;
  const originalRefreshSession = auth.refreshSession;
  const session = { access_token: "expired", user_id: "athlete-1" };
  const unauthorized = new ApiError("invalid authentication token", 401);
  const live = (token: string, userId = session.user_id) => ({
    data: { session: { access_token: token, user: { id: userId } } as Session },
    error: null,
  });
  let refreshes = 0;
  const reset = () => {
    refreshes = 0;
    auth.getSession = async () => live("expired");
    auth.refreshSession = async () => {
      refreshes += 1;
      return { ...live("fresh"), data: { ...live("fresh").data, user: null } };
    };
  };

  try {
    await t.test("all four history endpoints retry with the refreshed bearer token", async () => {
      for (const path of ["session-completions", "sparring-logs", "checkins", "injury-flags"]) {
        reset();
        const tokens: string[] = [];
        const result = await loadHistoryWithAuthRecovery(session, async (token) => {
          tokens.push(token);
          if (token === "expired") throw unauthorized;
          return [path];
        });
        assert.deepEqual(result, [path]);
        assert.deepEqual(tokens, ["expired", "fresh"]);
        assert.equal(refreshes, 1);
      }
    });
    await t.test("uses an already rotated token without forcing another refresh", async () => {
      reset();
      auth.getSession = async () => live("rotated");
      const result = await loadHistoryWithAuthRecovery(session, async (token) => {
        if (token === "expired") throw unauthorized;
        return token;
      });
      assert.equal(result, "rotated");
      assert.equal(refreshes, 0);
    });
    await t.test("a second 401 terminates recovery", async () => {
      reset();
      let requests = 0;
      await assert.rejects(loadHistoryWithAuthRecovery(session, async () => {
        requests += 1;
        throw unauthorized;
      }), unauthorized);
      assert.equal(requests, 2);
      assert.equal(refreshes, 1);
    });
    await t.test("never retries for a signed-out or different account", async () => {
      for (const current of [live("other", "athlete-2"), { data: { session: null }, error: null }]) {
        reset();
        auth.getSession = async () => current;
        let requests = 0;
        await assert.rejects(loadHistoryWithAuthRecovery(session, async () => {
          requests += 1;
          throw unauthorized;
        }), unauthorized);
        assert.equal(requests, 1);
        assert.equal(refreshes, 0);
      }
    });
    await t.test("does not retry after cancellation or for non-authentication failures", async () => {
      for (const [error, cancelled] of [[unauthorized, true], [new ApiError("Forbidden", 403), false]] as const) {
        reset();
        let requests = 0;
        await assert.rejects(loadHistoryWithAuthRecovery(session, async () => {
          requests += 1;
          throw error;
        }, () => cancelled), error);
        assert.equal(requests, 1);
        assert.equal(refreshes, 0);
      }
    });
    await t.test("rejects an account change returned by refresh", async () => {
      reset();
      auth.refreshSession = async () => ({
        ...live("other", "athlete-2"),
        data: { ...live("other", "athlete-2").data, user: null },
      });
      let requests = 0;
      await assert.rejects(loadHistoryWithAuthRecovery(session, async () => {
        requests += 1;
        throw unauthorized;
      }), unauthorized);
      assert.equal(requests, 1);
    });
  } finally {
    auth.getSession = originalGetSession;
    auth.refreshSession = originalRefreshSession;
    await auth.stopAutoRefresh();
  }
});
