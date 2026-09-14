import Module, { register, createRequire } from "node:module";

const require = createRequire(import.meta.url);
const englishMessages = require("../messages/en.json");

// The test files load via CommonJS (no "type": "module" in package.json), so
// tsx transpiles their `import` statements into `require()` calls. Node has
// no built-in require handler for `.css`, so without this it tries to parse
// stylesheet syntax as JavaScript and throws. Stub it out with an empty
// proxy, mirroring what a bundler would produce for a CSS module import.
Module._extensions[".css"] = (module) => {
  const classNames = new Proxy({}, { get: (_, prop) => String(prop) });
  module.exports = { __esModule: true, default: classNames };
};

// Component unit tests render isolated trees without the application-level
// NextIntlClientProvider. Give them the deterministic English catalog so the
// same UI assertions keep working after copy moves into message dictionaries.
const originalLoad = Module._load;
Module._load = function loadWithEnglishIntl(request, parent, isMain) {
  const loaded = originalLoad.call(this, request, parent, isMain);
  if (request !== "next-intl") return loaded;
  return {
    ...loaded,
    useTranslations(namespace) {
      return (key, values = {}) => {
        const value = namespace ? englishMessages[namespace]?.[key] : englishMessages[key];
        if (typeof value !== "string") return String(value ?? key);
        return value.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? `{${name}}`));
      };
    },
  };
};

// Also cover the ESM loader path, in case a test ever runs as a real ES module.
register("./css-stub-hooks.mjs", import.meta.url);
