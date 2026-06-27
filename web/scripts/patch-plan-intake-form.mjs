import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const intakePath = join(__dirname, "..", "components", "plan-intake-form.tsx");

const broken = `                      "Select days that can carry light technical combat: pads, drills, shadowboxing, movement, or non-hard contact. The app may still place low-noise support work here if it fits. Do not include hard sparring or fight day."
                  </p>`;
const fixed = `                      "Select days that can carry light technical combat: pads, drills, shadowboxing, movement, or non-hard contact. The app may still place low-noise support work here if it fits. Do not include hard sparring or fight day."}
                  </p>`;

const source = readFileSync(intakePath, "utf8");

if (source.includes(fixed)) {
  process.exit(0);
}

if (!source.includes(broken)) {
  throw new Error("Expected support_work_days helper text block was not found.");
}

writeFileSync(intakePath, source.replace(broken, fixed), "utf8");
