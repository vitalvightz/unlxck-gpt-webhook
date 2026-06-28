import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const intakePath = join(__dirname, "..", "components", "plan-intake-form.tsx");

const helperText =
  '"Select days that can carry light technical combat: pads, drills, shadowboxing, movement, or non-hard contact. The app may still place low-noise support work here if it fits. Do not include hard sparring or fight day."';
const fixedPattern = new RegExp(`${escapeRegExp(helperText)}\\s*}\\s*<\\/p>`);
const brokenPattern = new RegExp(`(${escapeRegExp(helperText)})(\\s*)<\\/p>`);

const source = readFileSync(intakePath, "utf8");

if (fixedPattern.test(source)) {
  process.exit(0);
}

if (!brokenPattern.test(source)) {
  throw new Error("Expected support_work_days helper text block was not found.");
}

writeFileSync(intakePath, source.replace(brokenPattern, "$1$2}$2</p>"), "utf8");

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
