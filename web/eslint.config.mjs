import next from "eslint-config-next";

/**
 * Practical, beta-readiness ESLint setup for the Next.js app.
 *
 * Extends the official `eslint-config-next` (Core Web Vitals) ruleset, which
 * focuses on real correctness/perf problems (hook dependencies, Next image/link
 * usage, etc.) rather than stylistic churn. We deliberately do not layer on the
 * full typescript-eslint recommended set here — typecheck (`tsc --noEmit`)
 * already guards types, and we want lint to stay fast and low-noise.
 */
const eslintConfig = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  ...next,
  {
    // The Next 16 ruleset enables the new React Compiler hook rules. Enforcing
    // `set-state-in-effect` / `purity` cleanly would require refactoring many
    // existing, working components, which is out of scope for this quality-gate
    // pass. Keep them as warnings so they surface without blocking CI; the rest
    // of the Core Web Vitals rules (real correctness/perf/a11y issues) stay on.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/purity": "warn",
    },
  },
];

export default eslintConfig;
