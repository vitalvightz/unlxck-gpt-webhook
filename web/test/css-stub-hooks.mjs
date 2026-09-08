// ESM loader hooks that stub out CSS (and CSS module) imports for the
// Node test runner, which has no bundler to turn `*.css` into JS.
export async function resolve(specifier, context, nextResolve) {
  if (specifier.endsWith(".css")) {
    return { url: `css-stub:${specifier}`, shortCircuit: true };
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
  return nextLoad(url, context);
}
