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

  // React assigns this from the nested Probe render. Copy through the declared
  // context type so TypeScript does not incorrectly narrow the closure-owned
  // variable to `never` after the null assertion.
  const current = value as ReturnType<typeof useXp> | null;
  assert.ok(current);
  assert.equal(current.isHydrated, true);
  assert.equal(current.progress.state.totalXp, 0);
  assert.equal(current.feedback, null);

  await act(async () => root.unmount());
  container.remove();
});
