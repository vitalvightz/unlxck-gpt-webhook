// Minimal jsdom bootstrap for interaction-level React tests run under
// `node --test` + tsx. Import this module for its side effect BEFORE rendering
// with react-dom/client; it installs the DOM globals React needs and flags the
// act() environment. renderToStaticMarkup tests are unaffected by a DOM being
// present, so this can coexist with the SSR tests in the same run.
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
  pretendToBeVisual: true,
});

const { window } = dom;

// Copy the DOM constructors/helpers React reads onto the Node global. navigator
// is a read-only getter on the Node global, so it is defined explicitly.
const globalAny = globalThis as unknown as Record<string, unknown>;
globalAny.window = window;
globalAny.document = window.document;
globalAny.HTMLElement = window.HTMLElement;
globalAny.Element = window.Element;
globalAny.Node = window.Node;
globalAny.Event = window.Event;
globalAny.MouseEvent = window.MouseEvent;
globalAny.getComputedStyle = window.getComputedStyle.bind(window);

Object.defineProperty(globalThis, "navigator", {
  value: window.navigator,
  configurable: true,
});

// React uses this flag to decide whether act() is required for updates.
globalAny.IS_REACT_ACT_ENVIRONMENT = true;

export { window };
