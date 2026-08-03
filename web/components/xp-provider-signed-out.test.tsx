import "./test-dom";

import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { AppSessionContext } from "./auth-provider";
import { XpProvider, useXp } from "./xp-provider";

test("signed-out users are hydrated immediately instead of seeing an endless XP skeleton", async () => {
  let value: ReturnType<typeof useXp> | null = null;
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);

  function Probe() {
    value = useXp();
    return null;
  }

  await act(async () => {
    root.render(
      <AppSessionContext.Provider value={{ session: null, me: null } as never}>
        <XpProvider>
          <Probe />
        </XpProvider>
      </AppSessionContext.Provider>,
    );
  });

  assert.ok(value);
  assert.equal(value.isHydrated, true);
  assert.equal(value.progress.state.totalXp, 0);
  assert.equal(value.feedback, null);

  await act(async () => root.unmount());
  container.remove();
});
