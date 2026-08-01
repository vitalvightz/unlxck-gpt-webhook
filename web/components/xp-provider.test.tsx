import "./test-dom";

import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { AppSessionContext } from "./auth-provider";
import {
  XP_AUTOMATIC_CLAIM_COOLDOWN_MS,
  XpProvider,
  useXp,
} from "./xp-provider";

type Identity = {
  athleteId: string;
  accessToken: string;
} | null;

type FetchCall = {
  url: string;
  authorization: string | null;
};

type FetchStub = {
  calls: FetchCall[];
  restore: () => void;
};

type Harness = {
  read: () => ReturnType<typeof useXp>;
  refresh: () => Promise<void>;
  renderIdentity: (identity: Identity) => Promise<void>;
  unmount: () => Promise<void>;
};

const BASE_TIME_MS = 1_800_000_000_000;

function dailyLoginResponse(totalXp = 10): Response {
  return new Response(
    JSON.stringify({
      state: {
        total_xp: totalXp,
        last_daily_login_date: "2026-08-01",
        recent_awards: [],
      },
      previous_total_xp: totalXp,
      awarded: false,
      award: null,
    }),
    {
      status: 200,
      headers: { "content-type": "application/json" },
    },
  );
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function installFetchStub(
  handler: (call: FetchCall, index: number) => Promise<Response> | Response,
): FetchStub {
  const originalFetch = globalThis.fetch;
  const calls: FetchCall[] = [];

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(typeof input === "string" || input instanceof URL ? input : input.url);
    const call = {
      url,
      authorization: new Headers(init?.headers).get("authorization"),
    };
    calls.push(call);
    return handler(call, calls.length - 1);
  }) as typeof fetch;

  return {
    calls,
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };
}

function sessionValue(identity: Identity) {
  if (!identity) {
    return {
      session: null,
      me: null,
    } as never;
  }

  return {
    session: { access_token: identity.accessToken },
    me: {
      profile: {
        role: "athlete",
        athlete_id: identity.athleteId,
      },
    },
  } as never;
}

async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function waitFor(predicate: () => boolean, message: string): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) {
      return;
    }
    await settle();
  }
  assert.fail(message);
}

async function mountProvider(identity: Identity): Promise<Harness> {
  let latestValue: ReturnType<typeof useXp> | null = null;
  const container = document.createElement("div");
  document.body.append(container);
  const root: Root = createRoot(container);

  function Probe() {
    latestValue = useXp();
    return null;
  }

  const renderIdentity = async (nextIdentity: Identity) => {
    await act(async () => {
      root.render(
        <AppSessionContext.Provider value={sessionValue(nextIdentity)}>
          <XpProvider>
            <Probe />
          </XpProvider>
        </AppSessionContext.Provider>,
      );
    });
    await settle();
  };

  await renderIdentity(identity);

  const read = () => {
    if (!latestValue) {
      throw new Error("XP provider never rendered.");
    }
    return latestValue;
  };

  return {
    read,
    refresh: async () => {
      await act(async () => {
        await read().refresh();
      });
      await settle();
    },
    renderIdentity,
    unmount: async () => {
      await act(async () => root.unmount());
      container.remove();
    },
  };
}

async function focusWindow(): Promise<void> {
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await settle();
}

function installClock(initialTimeMs = BASE_TIME_MS) {
  const originalNow = Date.now;
  let now = initialTimeMs;
  Date.now = () => now;
  return {
    set: (nextTimeMs: number) => {
      now = nextTimeMs;
    },
    restore: () => {
      Date.now = originalNow;
    },
  };
}

test("the first authenticated athlete load claims daily XP immediately", async () => {
  const clock = installClock();
  const fetchStub = installFetchStub(() => dailyLoginResponse());
  const harness = await mountProvider({ athleteId: "athlete-1", accessToken: "token-1" });

  try {
    await waitFor(() => harness.read().isHydrated, "initial XP claim did not finish");
    assert.equal(fetchStub.calls.length, 1);
    assert.equal(fetchStub.calls[0]?.url, "/api/xp/daily-login");
    assert.equal(fetchStub.calls[0]?.authorization, "Bearer token-1");
  } finally {
    await harness.unmount();
    fetchStub.restore();
    clock.restore();
  }
});

test("focus claims are suppressed for five minutes and resume at the boundary", async () => {
  const clock = installClock();
  const fetchStub = installFetchStub(() => dailyLoginResponse());
  const harness = await mountProvider({ athleteId: "athlete-1", accessToken: "token-1" });

  try {
    await waitFor(() => harness.read().isHydrated, "initial XP claim did not finish");
    clock.set(BASE_TIME_MS + XP_AUTOMATIC_CLAIM_COOLDOWN_MS - 1);
    await focusWindow();
    await focusWindow();
    assert.equal(fetchStub.calls.length, 1);

    clock.set(BASE_TIME_MS + XP_AUTOMATIC_CLAIM_COOLDOWN_MS);
    await focusWindow();
    await waitFor(() => fetchStub.calls.length === 2, "post-cooldown focus did not claim XP");
  } finally {
    await harness.unmount();
    fetchStub.restore();
    clock.restore();
  }
});

test("simultaneous focus and visibility events share the in-flight request", async () => {
  const clock = installClock();
  const pendingResponse = deferred<Response>();
  const fetchStub = installFetchStub(() => pendingResponse.promise);
  const harness = await mountProvider({ athleteId: "athlete-1", accessToken: "token-1" });

  try {
    await waitFor(() => fetchStub.calls.length === 1, "initial XP request did not start");
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      document.dispatchEvent(new Event("visibilitychange"));
    });
    assert.equal(fetchStub.calls.length, 1);

    await act(async () => pendingResponse.resolve(dailyLoginResponse()));
    await waitFor(() => harness.read().isHydrated, "shared XP request did not settle");
    assert.equal(fetchStub.calls.length, 1);
  } finally {
    await harness.unmount();
    fetchStub.restore();
    clock.restore();
  }
});

test("manual refresh bypasses the automatic cooldown", async () => {
  const clock = installClock();
  const fetchStub = installFetchStub(() => dailyLoginResponse());
  const harness = await mountProvider({ athleteId: "athlete-1", accessToken: "token-1" });

  try {
    await waitFor(() => harness.read().isHydrated, "initial XP claim did not finish");
    clock.set(BASE_TIME_MS + 1_000);
    await harness.refresh();
    assert.equal(fetchStub.calls.length, 2);

    await focusWindow();
    assert.equal(fetchStub.calls.length, 2, "manual completion should restart the cooldown");
  } finally {
    await harness.unmount();
    fetchStub.restore();
    clock.restore();
  }
});

test("switching athletes resets the cooldown without sharing account state", async () => {
  const clock = installClock();
  const fetchStub = installFetchStub(() => dailyLoginResponse());
  const harness = await mountProvider({ athleteId: "athlete-1", accessToken: "token-1" });

  try {
    await waitFor(() => harness.read().isHydrated, "first athlete XP claim did not finish");
    clock.set(BASE_TIME_MS + 1_000);
    await harness.renderIdentity({ athleteId: "athlete-2", accessToken: "token-2" });
    await waitFor(() => fetchStub.calls.length === 2, "second athlete XP claim did not start");
    assert.deepEqual(
      fetchStub.calls.map((call) => call.authorization),
      ["Bearer token-1", "Bearer token-2"],
    );
  } finally {
    await harness.unmount();
    fetchStub.restore();
    clock.restore();
  }
});

test("logout clears the previous athlete view and cooldown", async () => {
  const clock = installClock();
  const fetchStub = installFetchStub(() => dailyLoginResponse());
  const harness = await mountProvider({ athleteId: "athlete-1", accessToken: "token-1" });

  try {
    await waitFor(() => harness.read().isHydrated, "initial XP claim did not finish");
    assert.equal(harness.read().state.totalXp, 10);

    clock.set(BASE_TIME_MS + 1_000);
    await harness.renderIdentity(null);
    assert.equal(harness.read().state.totalXp, 0);
    assert.equal(harness.read().isHydrated, true);
    assert.equal(harness.read().dailyRewardStatus, "pending");

    await harness.renderIdentity({ athleteId: "athlete-1", accessToken: "token-2" });
    await waitFor(() => fetchStub.calls.length === 2, "login after logout did not claim XP");
  } finally {
    await harness.unmount();
    fetchStub.restore();
    clock.restore();
  }
});

test("failed automatic claims still start the five-minute cooldown", async () => {
  const clock = installClock();
  const fetchStub = installFetchStub(() => Promise.reject(new Error("XP unavailable")));
  const harness = await mountProvider({ athleteId: "athlete-1", accessToken: "token-1" });

  try {
    await waitFor(
      () => harness.read().dailyRewardStatus === "unavailable",
      "failed XP claim did not reach the unavailable state",
    );
    assert.equal(fetchStub.calls.length, 1);

    clock.set(BASE_TIME_MS + XP_AUTOMATIC_CLAIM_COOLDOWN_MS - 1);
    await focusWindow();
    assert.equal(fetchStub.calls.length, 1);

    clock.set(BASE_TIME_MS + XP_AUTOMATIC_CLAIM_COOLDOWN_MS);
    await focusWindow();
    await waitFor(() => fetchStub.calls.length === 2, "failed claim cooldown did not expire");
  } finally {
    await harness.unmount();
    fetchStub.restore();
    clock.restore();
  }
});
