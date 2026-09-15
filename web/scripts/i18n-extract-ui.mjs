import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import ts from "typescript";

import { isTranslatableUiText, NON_UI_CALLEE, UI_SINK_CALLEE } from "./i18n-ui-text-rules.mjs";

const webDirectory = path.resolve(import.meta.dirname, "..");
const sourceDirectories = ["app", "components"].map((directory) => path.join(webDirectory, directory));
const localeFiles = ["en", "es", "pt-BR", "fr", "it"].map((locale) => path.join(webDirectory, "messages", `${locale}.json`));
const dryRun = process.argv.includes("--check");
const translatableAttributes = new Set([
  "aria-label", "aria-description", "aria-valuetext", "ariaLabel", "alt", "title", "placeholder",
  "label", "description", "hint", "kicker", "eyebrow", "actionLabel", "triggerLabel", "emptyLabel",
  "railTitle", "railCopy", "statusMessage", "detailLabel", "disabledValueReason", "legend", "term", "example", "copy",
]);
const dataSourceFiles = [
  "lib/intake-options.ts", "lib/today.ts", "lib/xp.ts", "lib/admin-profile-warning.ts",
  "lib/profile-refresh-warning.ts", "lib/legal-documents.ts", "components/today/format.ts",
  "components/onboarding-trust-note.tsx", "components/generation-progress-milestones.tsx",
  "components/public-generation-screen.tsx", "components/premium-loading-screen.tsx",
  "components/push-notification-settings.tsx", "components/nutrition-subnav.tsx",
  "components/stage-one-preview-card.tsx", "components/rating-controls.tsx",
  "components/body-map.tsx", "components/guided-injury-card.tsx", "components/bodyweight-log-screen.tsx",
  "components/nutrition-workspace-screen.tsx", "components/plan-intake-form.tsx", "components/quick-build-form.tsx",
  "components/today/segment-group.tsx", "components/today/today-injury-manager.tsx",
  "lib/trust-copy.ts",
  "app/settings/page.tsx", "app/page.tsx",
].map((file) => path.join(webDirectory, file));
const translatableDataProperties = new Set([
  "label", "title", "description", "eyebrow", "actionText", "heading", "intro", "text", "body",
  "hint", "emptyTitle", "emptyText", "detail", "result_label", "caption", "help", "status",
  "statusMessage", "paragraphs", "bullets", "copy", "name",
]);
const translatableDataConstants = new Set(["TRUST_INTRO_HEADING", "TODAY_EMPTY_TITLE", "TODAY_EMPTY_TEXT"]);

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const target = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(target);
    if (!entry.isFile() || !entry.name.endsWith(".tsx") || entry.name.includes(".test.")) return [];
    return [target];
  }));
  return nested.flat();
}

function normalizeText(value) {
  return value.replace(/\s+/g, " ").trim();
}

function isTranslatable(value) {
  return /\p{L}/u.test(value);
}

/** The callee name of a call expression, without its receiver. */
function calleeName(node, sourceFile) {
  const text = node.expression.getText(sourceFile);
  return text.split(".").pop() ?? "";
}

function hashKey(value) {
  return `text_${createHash("sha256").update(value).digest("hex").slice(0, 12)}`;
}

function isFunction(node) {
  return ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node) || ts.isMethodDeclaration(node);
}

function componentName(node) {
  if (node.name && ts.isIdentifier(node.name)) return node.name.text;
  if (ts.isArrowFunction(node) || ts.isFunctionExpression(node)) {
    const declaration = node.parent;
    if (ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name)) return declaration.name.text;
    if (ts.isPropertyAssignment(declaration) && ts.isIdentifier(declaration.name)) return declaration.name.text;
  }
  return "";
}

function isComponentFunction(node) {
  const name = componentName(node);
  const defaultExport = node.modifiers?.some((modifier) => modifier.kind === ts.SyntaxKind.DefaultKeyword);
  return Boolean(defaultExport || /^[A-Z]/.test(name));
}

function nearestComponent(node) {
  for (let current = node.parent; current; current = current.parent) {
    if (isFunction(current) && isComponentFunction(current) && current.body && ts.isBlock(current.body)) return current;
  }
  return null;
}

function addEdit(edits, start, end, value) {
  edits.push({ start, end, value });
}

function applyEdits(source, edits) {
  return [...edits].sort((left, right) => right.start - left.start)
    .reduce((result, edit) => `${result.slice(0, edit.start)}${edit.value}${result.slice(edit.end)}`, source);
}

/**
 * Whether this node sits inside a callback passed to a React hook that takes a dependency
 * array (useEffect, useCallback, useMemo, useLayoutEffect).
 *
 * Copy is not extracted there. `appText` would become a value the callback closes over, and
 * the honest fix — listing it in the dependency array — re-runs the effect whenever the
 * translator's identity changes, which on a data-loading effect means refetching. These
 * sites keep the English string in state and are translated where the state is rendered,
 * with translateUiText(), so the stored value stays comparable and the effect stays inert.
 */
function insideHookCallbackWithDeps(node) {
  for (let current = node.parent; current; current = current.parent) {
    if (!ts.isArrowFunction(current) && !ts.isFunctionExpression(current)) continue;
    const call = current.parent;
    if (!ts.isCallExpression(call) || call.arguments[0] !== current) continue;
    const callee = call.expression.getText().split(".").pop() ?? "";
    if (/^use(?:Effect|LayoutEffect|Callback|Memo|InsertionEffect)$/.test(callee) && call.arguments.length > 1) {
      return true;
    }
  }
  return false;
}

/**
 * The outermost expression that still has this literal as one of its operands, climbing
 * through `?:`, `||`/`??` and parentheses. `cond ? "A" : x || "B"` resolves to the whole
 * expression, so the caller can ask where that expression's VALUE goes.
 */
function outermostOperand(node) {
  let current = node;
  while (
    current.parent
    && (ts.isBinaryExpression(current.parent)
      || ts.isConditionalExpression(current.parent)
      || ts.isParenthesizedExpression(current.parent))
  ) {
    current = current.parent;
  }
  return current;
}

/**
 * Whether this literal is one of the two terminal positions (see TERMINAL_POSITIONS in
 * i18n-ui-text-rules.mjs), and so safe to replace with a translation outright.
 *
 * Returns "" for everything else, including a literal whose value is assigned to a
 * variable: that value may be compared or used as a lookup key elsewhere, and only reading
 * the call site can tell. Those are localised by hand at the point of render.
 */
function terminalPosition(node, sourceFile) {
  const parent = node.parent;
  const isOperand =
    (ts.isBinaryExpression(parent)
      && parent.right === node
      && (parent.operatorToken.kind === ts.SyntaxKind.BarBarToken
        || parent.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken))
    || (ts.isConditionalExpression(parent) && (parent.whenTrue === node || parent.whenFalse === node));
  if (!isOperand && !(ts.isCallExpression(parent) && parent.arguments.includes(node))) return "";

  const outermost = isOperand ? outermostOperand(node) : node;
  const host = outermost.parent;

  if (ts.isCallExpression(host) && host.arguments.includes(outermost)) {
    const callee = host.expression.getText(sourceFile).split(".").pop() ?? "";
    if (NON_UI_CALLEE.test(callee)) return "";
    return UI_SINK_CALLEE.test(callee) ? "ui-sink-argument" : "";
  }
  // Rendered where it stands. A JSX attribute keeps the existing attribute allowlist, so a
  // className or an id is never treated as copy.
  if (ts.isJsxExpression(host)) {
    const attribute = ts.isJsxAttribute(host.parent) ? host.parent : null;
    if (!attribute) return "jsx-rendered";
    return translatableAttributes.has(attribute.name.getText(sourceFile)) ? "jsx-rendered" : "";
  }
  return "";
}

const files = (await Promise.all(sourceDirectories.map(sourceFiles))).flat();
const messages = new Map();
const perFile = new Map();
const skipped = [];
// Copy found outside any component: keyed and translated, but wired by hand.
const unscoped = [];
// Copy inside a hook callback with a dependency array: translated where it is rendered.
const renderSiteOnly = [];

for (const file of files) {
  const source = await readFile(file, "utf8");
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits = [];
  const functionsToUpdate = new Map();

  function visit(node) {
    let textNode = null;
    let rawText = "";
    let replacementStart = 0;
    let replacementEnd = 0;
    let expressionLiteral = false;

    if (ts.isJsxText(node)) {
      textNode = node;
      rawText = node.text;
      replacementStart = node.getStart(sourceFile);
      replacementEnd = node.getEnd();
    } else if (ts.isJsxAttribute(node) && translatableAttributes.has(node.name.getText(sourceFile)) && node.initializer && ts.isStringLiteral(node.initializer)) {
      textNode = node;
      rawText = node.initializer.text;
      replacementStart = node.initializer.getStart(sourceFile);
      replacementEnd = node.initializer.getEnd();
    } else if (ts.isStringLiteral(node) && ts.isConditionalExpression(node.parent) && (node.parent.whenTrue === node || node.parent.whenFalse === node)) {
      let conditional = node.parent;
      while (ts.isConditionalExpression(conditional.parent) && (conditional.parent.whenTrue === conditional || conditional.parent.whenFalse === conditional)) {
        conditional = conditional.parent;
      }
      const container = conditional.parent;
      const attribute = ts.isJsxExpression(container) && ts.isJsxAttribute(container.parent) ? container.parent : null;
      if (ts.isJsxExpression(container) && (!attribute || translatableAttributes.has(attribute.name.getText(sourceFile)))) {
        textNode = node;
        rawText = node.text;
        replacementStart = node.getStart(sourceFile);
        replacementEnd = node.getEnd();
        expressionLiteral = true;
      }
    }

    // The terminal positions the first pass never reached. They are held to the stricter copy
    // test in i18n-ui-text-rules.mjs, because unlike JSX text — which is copy by definition —
    // a literal here is just as likely to be a lookup key or a CSS class.
    let standalone = "";
    if (!textNode && ts.isStringLiteral(node)) {
      standalone = terminalPosition(node, sourceFile);
      if (standalone && insideHookCallbackWithDeps(node)) {
        renderSiteOnly.push({ file, text: normalizeText(node.text) });
        standalone = "";
      }
      if (standalone && isTranslatableUiText(node.text)) {
        textNode = node;
        rawText = node.text;
        replacementStart = node.getStart(sourceFile);
        replacementEnd = node.getEnd();
        expressionLiteral = true;
      } else {
        standalone = "";
      }
    }

    if (textNode) {
      const text = normalizeText(rawText);
      if (text && isTranslatable(text)) {
        const component = nearestComponent(textNode);
        if (!component) {
          // Outside a component there is no hook to call. The string still gets a key, so a
          // translation exists for it, and the call site is wired by hand with
          // translateUiText() where the value is rendered.
          if (standalone) {
            const key = hashKey(text);
            messages.set(key, text);
            unscoped.push({ file, text, key });
          } else {
            skipped.push({ file, text });
          }
        } else {
          const key = hashKey(text);
          const existing = messages.get(key);
          if (existing && existing !== text) throw new Error(`Message key collision: ${key}`);
          messages.set(key, text);
          addEdit(edits, replacementStart, replacementEnd, expressionLiteral ? `appText("${key}")` : `{appText("${key}")}`);
          if (!component.body.getText(sourceFile).includes('useAppTranslations("AppText")')) {
            const position = component.body.getStart(sourceFile) + 1;
            functionsToUpdate.set(position, position);
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  if (!edits.length) continue;

  for (const position of functionsToUpdate.keys()) addEdit(edits, position, position, `\n    const appText = useAppTranslations("AppText");`);

  const hasAppTranslator = source.includes('useTranslations as useAppTranslations } from "next-intl"');
  if (!hasAppTranslator) {
    const importStatements = sourceFile.statements.filter(ts.isImportDeclaration);
    const directive = sourceFile.statements.find((statement) =>
      ts.isExpressionStatement(statement) && ts.isStringLiteral(statement.expression),
    );
    const importPosition = importStatements.at(-1)?.end ?? directive?.end ?? 0;
    addEdit(edits, importPosition, importPosition, `\nimport { useTranslations as useAppTranslations } from "next-intl";`);
  }

  perFile.set(file, { edits, count: edits.filter((edit) => edit.value.startsWith("{appText(")).length });
}

for (const file of dataSourceFiles) {
  const source = await readFile(file, "utf8");
  const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  function visitData(node) {
    if (ts.isStringLiteral(node)) {
      if (ts.isVariableDeclaration(node.parent) && ts.isIdentifier(node.parent.name) && translatableDataConstants.has(node.parent.name.text)) {
        const text = normalizeText(node.text);
        if (text && isTranslatable(text)) messages.set(hashKey(text), text);
      }
      let current = node.parent;
      while (current && !ts.isPropertyAssignment(current)) current = current.parent;
      const propertyName = current && (ts.isIdentifier(current.name) || ts.isStringLiteral(current.name)) ? current.name.text : "";
      if (translatableDataProperties.has(propertyName)) {
        const text = normalizeText(node.text);
        if (text && isTranslatable(text)) messages.set(hashKey(text), text);
      }
    }
    ts.forEachChild(node, visitData);
  }
  visitData(sourceFile);
}

if (skipped.length) {
  console.error(`Skipped ${skipped.length} JSX text node(s) without a recognized component scope.`);
  for (const item of skipped.slice(0, 20)) console.error(`${path.relative(webDirectory, item.file)}: ${item.text}`);
}

if (renderSiteOnly.length) {
  const distinct = [...new Set(renderSiteOnly.map((item) => `${path.relative(webDirectory, item.file)}  ${JSON.stringify(item.text)}`))];
  console.log(`${distinct.length} string(s) sit in a hook callback and are translated at the render site instead:`);
  for (const line of distinct) console.log(`  ${line}`);
}

if (unscoped.length) {
  console.log(`${unscoped.length} string(s) are outside a component and need translateUiText() at the render site:`);
  for (const item of unscoped) {
    console.log(`  ${path.relative(webDirectory, item.file)}  ${item.key}  ${JSON.stringify(item.text)}`);
  }
}

if (dryRun) {
  const english = JSON.parse(await readFile(localeFiles[0], "utf8")).AppText ?? {};
  const missing = [...messages.keys()].filter((key) => !(key in english));
  console.log(`Checked ${messages.size} unique UI strings across ${perFile.size} files; ${missing.length} absent from English, ${skipped.length} node(s) skipped.`);
  if (missing.length) console.error(`Missing English keys: ${missing.join(", ")}`);
  process.exitCode = skipped.length || missing.length ? 1 : 0;
} else {
  for (const [file, { edits }] of perFile) {
    const source = await readFile(file, "utf8");
    await writeFile(file, applyEdits(source, edits), "utf8");
  }

  const catalogs = await Promise.all(localeFiles.map(async (file) => JSON.parse(await readFile(file, "utf8"))));
  const [english, ...targets] = catalogs;
  english.AppText = {
    ...english.AppText,
    ...Object.fromEntries([...messages.entries()].sort(([left], [right]) => left.localeCompare(right))),
  };
  for (const target of targets) {
    target.AppText ??= {};
  }

  await Promise.all(localeFiles.map((file, index) => writeFile(file, `${JSON.stringify(catalogs[index], null, 2)}\n`, "utf8")));
  console.log(`Extracted ${messages.size} unique UI strings across ${perFile.size} files; skipped ${skipped.length} node(s).`);
}
