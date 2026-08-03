import test from "node:test";
import assert from "node:assert/strict";

// Installs the jsdom globals for react-dom/client. Must run before the client
// renderer / component are exercised (the import side effect handles that).
import "./test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { WhyTooltip } from "./why-tooltip";

function mount(): { container: HTMLElement; root: Root } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  return { container, root };
}

function cleanup(container: HTMLElement, root: Root) {
  act(() => {
    root.unmount();
  });
  container.remove();
}

/** jsdom gives every element a zero rect, so the geometry under test has to be
 * supplied. Stubs the trigger's position and the bubble's measured size. */
function stubGeometry(
  trigger: HTMLElement,
  triggerRect: { top: number; left: number; width: number; height: number },
) {
  trigger.getBoundingClientRect = () =>
    ({
      top: triggerRect.top,
      bottom: triggerRect.top + triggerRect.height,
      left: triggerRect.left,
      right: triggerRect.left + triggerRect.width,
      width: triggerRect.width,
      height: triggerRect.height,
      x: triggerRect.left,
      y: triggerRect.top,
      toJSON: () => ({}),
    }) as DOMRect;
}

function stubBubbleSize(bubble: HTMLElement, width: number, height: number) {
  const original = bubble.getBoundingClientRect.bind(bubble);
  bubble.getBoundingClientRect = () => {
    const rect = original();
    return { ...rect, width, height, toJSON: () => ({}) } as DOMRect;
  };
}

async function openTooltip(
  container: HTMLElement,
  root: Root,
  triggerRect: { top: number; left: number; width: number; height: number },
  bubbleSize: { width: number; height: number },
): Promise<HTMLElement> {
  await act(async () => {
    root.render(<WhyTooltip title="RPE" body="How hard it should feel." triggerLabel="?" />);
  });

  const trigger = container.querySelector<HTMLButtonElement>(".why-tooltip-trigger");
  assert.ok(trigger, "expected a trigger button");
  stubGeometry(trigger, triggerRect);

  // First click mounts the bubble so it can be measured, then a resize forces
  // the position pass to run again against the stubbed size.
  await act(async () => {
    trigger.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
  const bubble = document.body.querySelector<HTMLElement>(".why-tooltip-bubble");
  assert.ok(bubble, "expected the bubble to be portalled onto <body>");
  stubBubbleSize(bubble, bubbleSize.width, bubbleSize.height);
  await act(async () => {
    window.dispatchEvent(new window.Event("resize"));
  });
  return bubble;
}

test("the bubble is portalled onto <body>, not left inside the clipping parent", async () => {
  // The regression: an absolutely-positioned bubble was clipped by any ancestor
  // with overflow:hidden (the plan accordion), so the explanation was unreadable
  // exactly where the jargon appears.
  const { container, root } = mount();
  container.style.overflow = "hidden";
  try {
    const bubble = await openTooltip(
      container,
      root,
      { top: 300, left: 400, width: 16, height: 16 },
      { width: 320, height: 120 },
    );
    assert.equal(bubble.parentElement, document.body);
    assert.equal(container.querySelector(".why-tooltip-bubble"), null);
  } finally {
    cleanup(container, root);
  }
});

test("a trigger at the right edge pulls the bubble back inside the viewport", async () => {
  const { container, root } = mount();
  try {
    // 1024px-wide jsdom viewport; a 320px bubble centred on x=1016 would run
    // ~170px off-screen without clamping.
    const bubble = await openTooltip(
      container,
      root,
      { top: 300, left: 1008, width: 16, height: 16 },
      { width: 320, height: 120 },
    );
    const left = Number.parseFloat(bubble.style.left);
    assert.ok(left >= 0, `bubble left ${left} should not be negative`);
    assert.ok(left + 320 <= 1024, `bubble right edge ${left + 320} should stay inside 1024px`);
  } finally {
    cleanup(container, root);
  }
});

test("a trigger at the left edge is clamped the same way", async () => {
  const { container, root } = mount();
  try {
    const bubble = await openTooltip(
      container,
      root,
      { top: 300, left: 4, width: 16, height: 16 },
      { width: 320, height: 120 },
    );
    assert.ok(Number.parseFloat(bubble.style.left) >= 0);
  } finally {
    cleanup(container, root);
  }
});

test("a trigger near the top of the screen flips the bubble below it", async () => {
  const { container, root } = mount();
  try {
    const bubble = await openTooltip(
      container,
      root,
      { top: 12, left: 400, width: 16, height: 16 },
      { width: 320, height: 200 },
    );
    assert.equal(bubble.dataset.placement, "below");
    assert.ok(
      Number.parseFloat(bubble.style.top) >= 28,
      "a flipped bubble should sit under the trigger, not over it",
    );
  } finally {
    cleanup(container, root);
  }
});

test("a trigger near the bottom keeps the bubble above and fully on screen", async () => {
  const { container, root } = mount();
  try {
    const bubble = await openTooltip(
      container,
      root,
      { top: 740, left: 400, width: 16, height: 16 },
      { width: 320, height: 160 },
    );
    assert.equal(bubble.dataset.placement, "above");
    const top = Number.parseFloat(bubble.style.top);
    assert.ok(top >= 0, `bubble top ${top} should not be negative`);
    assert.ok(top + 160 <= 768, `bubble bottom ${top + 160} should stay inside 768px`);
  } finally {
    cleanup(container, root);
  }
});

test("the arrow stays within the bubble after it has been clamped sideways", async () => {
  const { container, root } = mount();
  try {
    const bubble = await openTooltip(
      container,
      root,
      { top: 300, left: 1008, width: 16, height: 16 },
      { width: 320, height: 120 },
    );
    const arrow = Number.parseFloat(bubble.style.getPropertyValue("--why-tooltip-arrow-left"));
    assert.ok(Number.isFinite(arrow), "expected an arrow offset to be set");
    assert.ok(arrow >= 0 && arrow <= 320, `arrow offset ${arrow} should sit inside the bubble`);
  } finally {
    cleanup(container, root);
  }
});

test("Escape closes the bubble", async () => {
  const { container, root } = mount();
  try {
    await openTooltip(
      container,
      root,
      { top: 300, left: 400, width: 16, height: 16 },
      { width: 320, height: 120 },
    );
    await act(async () => {
      document.dispatchEvent(
        new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }),
      );
    });
    assert.equal(document.body.querySelector(".why-tooltip-bubble"), null);
  } finally {
    cleanup(container, root);
  }
});

test("a pointer press inside the portalled bubble does not dismiss it", async () => {
  // The bubble now lives outside the trigger's container, so the outside-click
  // guard has to check the bubble too or its own copy would close it.
  const { container, root } = mount();
  try {
    const bubble = await openTooltip(
      container,
      root,
      { top: 300, left: 400, width: 16, height: 16 },
      { width: 320, height: 120 },
    );
    const body = bubble.querySelector(".why-tooltip-body");
    assert.ok(body);
    await act(async () => {
      body.dispatchEvent(new window.Event("pointerdown", { bubbles: true }));
    });
    assert.ok(document.body.querySelector(".why-tooltip-bubble"), "bubble should stay open");

    await act(async () => {
      document.body.dispatchEvent(new window.Event("pointerdown", { bubbles: true }));
    });
    assert.equal(
      document.body.querySelector(".why-tooltip-bubble"),
      null,
      "a press outside should still close it",
    );
  } finally {
    cleanup(container, root);
  }
});

/** A touch tap as browsers actually deliver it: a synthesized mouseover lands
 * BEFORE the click, so the tooltip is already hover-open by the time the click
 * is handled. */
async function tap(trigger: HTMLElement) {
  await act(async () => {
    trigger.dispatchEvent(
      new window.MouseEvent("mouseover", { bubbles: true, relatedTarget: document.body }),
    );
  });
  await act(async () => {
    trigger.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
}

test("a tap still opens the tooltip even though hover fired first", async () => {
  // The regression: a plain toggle read the hover-open state and closed again on
  // the very same tap, so on a phone the "?" could never be read at all.
  const { container, root } = mount();
  try {
    await act(async () => {
      root.render(<WhyTooltip title="RPE" body="How hard it should feel." triggerLabel="?" />);
    });
    const trigger = container.querySelector<HTMLButtonElement>(".why-tooltip-trigger");
    assert.ok(trigger);
    stubGeometry(trigger, { top: 300, left: 400, width: 16, height: 16 });

    await tap(trigger);
    assert.ok(document.body.querySelector(".why-tooltip-bubble"), "a tap must leave the bubble open");
  } finally {
    cleanup(container, root);
  }
});

test("a pinned bubble survives the pointer leaving, and a second tap dismisses it", async () => {
  const { container, root } = mount();
  try {
    await act(async () => {
      root.render(<WhyTooltip title="RPE" body="How hard it should feel." triggerLabel="?" />);
    });
    const trigger = container.querySelector<HTMLButtonElement>(".why-tooltip-trigger");
    assert.ok(trigger);
    stubGeometry(trigger, { top: 300, left: 400, width: 16, height: 16 });

    await tap(trigger);
    // Touch devices emit a trailing mouseout; that must not undo a deliberate tap.
    await act(async () => {
      trigger.dispatchEvent(
        new window.MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }),
      );
      await new Promise((resolve) => setTimeout(resolve, 200));
    });
    assert.ok(document.body.querySelector(".why-tooltip-bubble"), "a pinned bubble should persist");

    await tap(trigger);
    assert.equal(
      document.body.querySelector(".why-tooltip-bubble"),
      null,
      "tapping the trigger again should dismiss it",
    );
  } finally {
    cleanup(container, root);
  }
});

test("hover alone opens the bubble and moving away closes it", async () => {
  const { container, root } = mount();
  try {
    await act(async () => {
      root.render(<WhyTooltip title="RPE" body="How hard it should feel." triggerLabel="?" />);
    });
    const trigger = container.querySelector<HTMLButtonElement>(".why-tooltip-trigger");
    assert.ok(trigger);
    stubGeometry(trigger, { top: 300, left: 400, width: 16, height: 16 });

    await act(async () => {
      trigger.dispatchEvent(
        new window.MouseEvent("mouseover", { bubbles: true, relatedTarget: document.body }),
      );
    });
    assert.ok(document.body.querySelector(".why-tooltip-bubble"), "hover should open it");

    await act(async () => {
      trigger.dispatchEvent(
        new window.MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }),
      );
      await new Promise((resolve) => setTimeout(resolve, 200));
    });
    assert.equal(
      document.body.querySelector(".why-tooltip-bubble"),
      null,
      "an unpinned bubble closes when the pointer leaves",
    );
  } finally {
    cleanup(container, root);
  }
});
