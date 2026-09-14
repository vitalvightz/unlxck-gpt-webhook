import Module, { register } from "node:module";

// The test files load via CommonJS (no "type": "module" in package.json), so
// tsx transpiles their `import` statements into `require()` calls. Node has
// no built-in require handler for `.css`, so without this it tries to parse
// stylesheet syntax as JavaScript and throws. Stub it out with an empty
// proxy, mirroring what a bundler would produce for a CSS module import.
Module._extensions[".css"] = (module) => {
  const classNames = new Proxy({}, { get: (_, prop) => String(prop) });
  module.exports = { __esModule: true, default: classNames };
};

// Also cover the ESM loader path, in case a test ever runs as a real ES module.
register("./css-stub-hooks.mjs", import.meta.url);
