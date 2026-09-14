// ESM loader hooks for the Node test runner, which has no bundler: CSS (and CSS module)
// imports become an empty proxy, and next-intl's client hooks resolve to the English
// catalog so component tests can render without the application-level provider.
//
// The CommonJS side of this lives in test/register-css-stub.mjs. Both paths are needed:
// on Node 22 a .tsx test transpiled by tsx reaches next-intl through `require`, while on
// Node 24 (the version package.json asks for) the same import is served by these hooks,
// and a stub on only one of the two leaves half the suite without a provider.
const INTL_STUB_URL = "next-intl-stub:english";

// tsx's own resolve hook runs ahead of this one and hands on the fully resolved file
// URL, so the bare specifier alone is not enough to catch the import.
const isNextIntl = (specifier) =>
  specifier === "next-intl" || /[\\/]next-intl[\\/]dist[\\/].*react-client/.test(specifier);

export async function resolve(specifier, context, nextResolve) {
  if (specifier.endsWith(".css")) {
    return { url: `css-stub:${specifier}`, shortCircuit: true };
  }
  if (isNextIntl(specifier)) {
    return { url: INTL_STUB_URL, shortCircuit: true };
  }
  return nextResolve(specifier, context);
}

export async function load(url, context, nextLoad) {
  if (url.startsWith("css-stub:")) {
    return {
      format: "module",
      shortCircuit: true,
      source:
        "const classNames = new Proxy({}, { get: (_, prop) => String(prop) }); export default classNames;",
    };
  }
  if (url === INTL_STUB_URL || isNextIntl(url)) {
    return {
      format: "module",
      shortCircuit: true,
      source: `
        import { createRequire } from "node:module";
        const require = createRequire(${JSON.stringify(import.meta.url)});
        const englishMessages = require("../messages/en.json");
        export function useTranslations(namespace) {
          return (key, values = {}) => {
            const value = namespace ? englishMessages[namespace]?.[key] : englishMessages[key];
            if (typeof value !== "string") return String(value ?? key);
            return value.replace(/\\{(\\w+)\\}/g, (_, name) => String(values[name] ?? \`{\${name}}\`));
          };
        }
        export function useLocale() {
          return "en";
        }
        export function NextIntlClientProvider({ children }) {
          return children;
        }
      `,
    };
  }
  return nextLoad(url, context);
}
