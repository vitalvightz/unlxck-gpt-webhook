#!/usr/bin/env node
// Summarises raw e2e/frontend-requests.spec.ts benchmark files (FRONTEND_BENCH_OUT)
// into the compact comparison committed under docs/performance/.
//
//   node scripts/summarise-request-benchmark.mjs --pair 150 before-150.json after-150.json \
//     --pair 600 before-600.json after-600.json --output ../docs/performance/frontend-comparison.json
import { readFileSync, writeFileSync } from "node:fs";

const args = process.argv.slice(2);
const pairs = [];
let output = null;
for (let index = 0; index < args.length; index += 1) {
  if (args[index] === "--pair") {
    pairs.push({ label: args[index + 1], before: args[index + 2], after: args[index + 3] });
    index += 3;
  } else if (args[index] === "--output") {
    output = args[index + 1];
    index += 1;
  } else {
    throw new Error(`Unknown argument ${args[index]}`);
  }
}
if (!pairs.length) throw new Error("Pass at least one --pair <label> <before.json> <after.json>");

// Nearest rank, as in docs/performance/backend-optimisation-results.md.
function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil((p / 100) * sorted.length) - 1)];
}
const endpoint = (path) => path.split("?")[0].replace(/^\/api\/plans\/[0-9a-f-]{36}/, "/api/plans/:id")
  .replace(/^\/api\/training\/history\/[^/]+\/.+$/, "/api/training/history/:source/:id");
const range = (values) => {
  const min = Math.min(...values); const max = Math.max(...values);
  return min === max ? min : [min, max];
};

function duplicates(requests) {
  const seen = new Set(); let repeated = 0;
  for (const { method, path } of requests) {
    if (method !== "GET") continue;
    if (seen.has(path)) repeated += 1; else seen.add(path);
  }
  return repeated;
}

function summarise(file) {
  const { latencyMs, runs, results } = JSON.parse(readFileSync(file, "utf8"));
  const journeys = results[0].map((step) => step.journey);
  const steps = journeys.map((journey, index) => {
    const samples = results.map((run) => run[index]);
    if (samples.some((sample) => sample.journey !== journey)) throw new Error(`Journey order differs in ${file}`);
    const endpoints = {};
    for (const sample of samples) {
      for (const request of sample.requests) {
        const key = `${request.method} ${endpoint(request.path)}`;
        endpoints[key] = (endpoints[key] ?? 0) + 1 / samples.length;
      }
    }
    return {
      journey,
      requests: range(samples.map((sample) => sample.requests.length)),
      gets: range(samples.map((sample) => sample.requests.filter((request) => request.method === "GET").length)),
      duplicateGets: range(samples.map((sample) => duplicates(sample.requests))),
      responseBytes: range(samples.map((sample) => sample.requests.reduce((total, request) => total + request.bytes, 0))),
      usefulMs: { p50: percentile(samples.map((sample) => sample.usefulMs), 50), p95: percentile(samples.map((sample) => sample.usefulMs), 95) },
      readyMs: { p50: percentile(samples.map((sample) => sample.readyMs), 50), p95: percentile(samples.map((sample) => sample.readyMs), 95) },
      meanEndpointCalls: Object.fromEntries(Object.entries(endpoints).sort().map(([key, value]) => [key, Math.round(value * 100) / 100])),
    };
  });
  return { latencyMs, runs, steps };
}

const comparison = pairs.map(({ label, before, after }) => {
  const b = summarise(before); const a = summarise(after);
  return {
    label, latencyMs: a.latencyMs, runs: { before: b.runs, after: a.runs },
    journeys: b.steps.map((step, index) => {
      const next = a.steps[index];
      if (next?.journey !== step.journey) throw new Error("Before and after journeys differ");
      const avoided = {};
      for (const key of new Set([...Object.keys(step.meanEndpointCalls), ...Object.keys(next.meanEndpointCalls)])) {
        const delta = Math.round(((step.meanEndpointCalls[key] ?? 0) - (next.meanEndpointCalls[key] ?? 0)) * 100) / 100;
        if (delta) avoided[key] = delta;
      }
      return { journey: step.journey, before: step, after: next, endpointCallsAvoided: avoided };
    }),
  };
});

const fmt = (value) => (Array.isArray(value) ? `${value[0]}–${value[1]}` : String(value));
for (const { label, latencyMs, runs, journeys } of comparison) {
  console.log(`\n${label}: ${latencyMs} ms mocked API latency, ${runs.before}/${runs.after} runs`);
  console.log("| Journey | Before requests | After requests | Before useful p50/p95 ms | After useful p50/p95 ms | Before ready p50/p95 ms | After ready p50/p95 ms |");
  console.log("| --- | ---: | ---: | ---: | ---: | ---: | ---: |");
  for (const { journey, before, after } of journeys) {
    console.log(`| ${journey} | ${fmt(before.requests)} | ${fmt(after.requests)} | ${before.usefulMs.p50} / ${before.usefulMs.p95} | ${after.usefulMs.p50} / ${after.usefulMs.p95} | ${before.readyMs.p50} / ${before.readyMs.p95} | ${after.readyMs.p50} / ${after.readyMs.p95} |`);
  }
}
if (output) writeFileSync(output, `${JSON.stringify({ comparison }, null, 1)}\n`);
