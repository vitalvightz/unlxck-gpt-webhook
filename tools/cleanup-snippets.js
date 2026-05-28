#!/usr/bin/env node
/**
 * cleanup-snippets.js
 * -------------------
 * Safely triage saved Supabase SQL snippets stored in a local `snippets.json`
 * file.
 *
 * IMPORTANT SAFETY NOTES:
 *   - This script NEVER connects to Supabase or any database.
 *   - It NEVER touches tables, rows, policies, schema, or RLS.
 *   - It only reads/writes the LOCAL `snippets.json` file you exported.
 *   - By default it is a DRY-RUN: it writes plan files and changes nothing.
 *   - It only rewrites snippets.json (removing the delete-plan items) when you
 *     explicitly set the environment variable DELETE_SNIPPETS=1.
 *   - Before any rewrite, it makes a timestamped backup of snippets.json.
 *
 * Triage logic (per snippet):
 *   - If a snippet has NO id OR NO title  -> always goes to "review needed"
 *     (never auto-deleted).
 *   - If the title OR the SQL body matches any KEEP keyword -> "keep".
 *   - Everything else -> "delete plan" (candidate for deletion).
 *
 * Outputs (always written, even in dry-run):
 *   - snippets-keep-plan.json
 *   - snippets-delete-plan.json
 *   - snippets-review-needed.json
 *
 * Usage:
 *   node tools/cleanup-snippets.js              # dry-run (default, safe)
 *   DELETE_SNIPPETS=1 node tools/cleanup-snippets.js   # actually rewrite
 *
 * On Windows PowerShell, see the instructions printed at the bottom of the
 * console output and in the chat reply.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Resolve snippets.json relative to the current working directory so you can
// run the script from wherever your export lives.
const SNIPPETS_PATH = path.resolve(process.cwd(), 'snippets.json');
const OUT_DIR = process.cwd();

const KEEP_PLAN_PATH = path.join(OUT_DIR, 'snippets-keep-plan.json');
const DELETE_PLAN_PATH = path.join(OUT_DIR, 'snippets-delete-plan.json');
const REVIEW_PATH = path.join(OUT_DIR, 'snippets-review-needed.json');

// Keywords that mark a snippet as worth KEEPING. Matched case-insensitively
// against both the snippet title/name AND the SQL body/content.
const KEEP_KEYWORDS = [
  'migration', 'migrations',
  'schema',
  'rls', 'row level security', 'row-level security',
  'policy', 'policies',
  'trigger', 'triggers',
  'function', 'functions',
  'production', 'prod',
  'index', 'indexes', 'indices',
  'constraint', 'constraints',
  'backup', 'backups',
  'cron',
  'admin',
  'auth',
  'profile', 'profiles',
  'role', 'roles',
  'plan', 'plans',
  'athlete', 'athletes',
  'storage',
  'bucket', 'buckets',
  'service role', 'service_role',
  'webhook', 'webhooks',
  'supabase',
];

// Build a single case-insensitive regex from the keywords. We use word-ish
// boundaries so "plan" matches "plans" / "plan_id" but not random substrings
// inside unrelated words. Keywords are escaped so special chars are literal.
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
const KEEP_REGEX = new RegExp(
  '(^|[^a-z0-9])(' + KEEP_KEYWORDS.map(escapeRegex).join('|') + ')([^a-z0-9]|$)',
  'i'
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fail(message) {
  console.error('\n[ERROR] ' + message + '\n');
  process.exit(1);
}

function timestamp() {
  // e.g. 2026-05-28T13-45-09-123Z  (filesystem-safe, no ":" which Windows hates)
  return new Date().toISOString().replace(/[:.]/g, '-');
}

// Pull the title/name from a snippet regardless of which field name is used.
function getTitle(snippet) {
  if (!snippet || typeof snippet !== 'object') return '';
  const candidates = [snippet.title, snippet.name, snippet.label];
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim() !== '') return c.trim();
  }
  return '';
}

// Pull the SQL body/content from a snippet regardless of which field name is used.
function getBody(snippet) {
  if (!snippet || typeof snippet !== 'object') return '';
  const candidates = [
    snippet.sql,
    snippet.content,
    snippet.body,
    snippet.query,
    snippet.code,
  ];
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim() !== '') return c.trim();
  }
  return '';
}

// Pull the id regardless of field name.
function getId(snippet) {
  if (!snippet || typeof snippet !== 'object') return undefined;
  const candidates = [snippet.id, snippet.uuid, snippet._id, snippet.snippet_id];
  for (const c of candidates) {
    if (c !== undefined && c !== null && String(c).trim() !== '') return c;
  }
  return undefined;
}

function matchedKeywords(text) {
  if (!text) return [];
  const found = new Set();
  for (const kw of KEEP_KEYWORDS) {
    const re = new RegExp(
      '(^|[^a-z0-9])(' + escapeRegex(kw) + ')([^a-z0-9]|$)',
      'i'
    );
    if (re.test(text)) found.add(kw);
  }
  return Array.from(found);
}

function writeJson(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n', 'utf8');
}

// ---------------------------------------------------------------------------
// Load snippets.json
// ---------------------------------------------------------------------------

if (!fs.existsSync(SNIPPETS_PATH)) {
  fail(
    'Could not find snippets.json at:\n  ' + SNIPPETS_PATH +
    '\nRun this script from the folder that contains snippets.json.'
  );
}

let raw;
try {
  raw = fs.readFileSync(SNIPPETS_PATH, 'utf8');
} catch (e) {
  fail('Failed to read snippets.json: ' + e.message);
}

let parsed;
try {
  parsed = JSON.parse(raw);
} catch (e) {
  fail('snippets.json is not valid JSON: ' + e.message);
}

// Accept either a bare array, or an object wrapping the array under a common key.
let snippets;
let containerKey = null; // remember the wrapping key so we can write it back
if (Array.isArray(parsed)) {
  snippets = parsed;
} else if (parsed && typeof parsed === 'object') {
  const key = ['snippets', 'data', 'items', 'results'].find(
    (k) => Array.isArray(parsed[k])
  );
  if (!key) {
    fail(
      'snippets.json is a JSON object but no snippet array was found under ' +
      '"snippets", "data", "items", or "results".'
    );
  }
  containerKey = key;
  snippets = parsed[key];
} else {
  fail('snippets.json must contain a JSON array of snippets.');
}

console.log('Loaded ' + snippets.length + ' snippets from snippets.json');

// ---------------------------------------------------------------------------
// Triage
// ---------------------------------------------------------------------------

const keepPlan = [];
const deletePlan = [];
const reviewNeeded = [];

snippets.forEach((snippet, index) => {
  const id = getId(snippet);
  const title = getTitle(snippet);
  const body = getBody(snippet);

  const record = {
    index,
    id: id !== undefined ? id : null,
    title: title || null,
    bodyPreview: body ? body.slice(0, 200) : null,
  };

  // Rule 5: never auto-delete snippets with no title OR no id.
  if (id === undefined || title === '') {
    record.reason =
      'Missing ' +
      [id === undefined ? 'id' : null, title === '' ? 'title' : null]
        .filter(Boolean)
        .join(' and ') +
      ' — requires manual review (never auto-deleted).';
    reviewNeeded.push(record);
    return;
  }

  // Rule 4: keep anything that matches a keep keyword in title OR body.
  const titleHits = matchedKeywords(title);
  const bodyHits = matchedKeywords(body);
  const allHits = Array.from(new Set([...titleHits, ...bodyHits]));

  if (allHits.length > 0) {
    record.matchedKeywords = allHits;
    record.matchedIn = [
      titleHits.length ? 'title' : null,
      bodyHits.length ? 'body' : null,
    ].filter(Boolean);
    keepPlan.push(record);
    return;
  }

  // Otherwise: deletion candidate.
  record.reason = 'No keep keyword matched in title or SQL body.';
  deletePlan.push(record);
});

// ---------------------------------------------------------------------------
// Write plan files (always — even in dry-run)
// ---------------------------------------------------------------------------

writeJson(KEEP_PLAN_PATH, keepPlan);
writeJson(DELETE_PLAN_PATH, deletePlan);
writeJson(REVIEW_PATH, reviewNeeded);

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

const DELETE_MODE = process.env.DELETE_SNIPPETS === '1';

console.log('\n=========== SNIPPET TRIAGE SUMMARY ===========');
console.log('Total snippets:        ' + snippets.length);
console.log('KEEP (protected):      ' + keepPlan.length);
console.log('DELETE candidates:     ' + deletePlan.length);
console.log('REVIEW needed:         ' + reviewNeeded.length);
console.log('----------------------------------------------');
console.log('Plan files written:');
console.log('  ' + KEEP_PLAN_PATH);
console.log('  ' + DELETE_PLAN_PATH);
console.log('  ' + REVIEW_PATH);
console.log('==============================================\n');

if (!DELETE_MODE) {
  console.log('DRY-RUN MODE (default). Nothing was deleted or modified.');
  console.log('snippets.json is untouched.');
  console.log('');
  console.log('Review snippets-delete-plan.json carefully.');
  console.log('When you are happy, re-run with DELETE_SNIPPETS=1 to apply.');
  process.exit(0);
}

// ---------------------------------------------------------------------------
// DELETE MODE — only reached when DELETE_SNIPPETS=1
// ---------------------------------------------------------------------------

if (deletePlan.length === 0) {
  console.log('DELETE_SNIPPETS=1 set, but there is nothing to delete. Done.');
  process.exit(0);
}

console.log('!!! DELETE MODE ENABLED (DELETE_SNIPPETS=1) !!!');
console.log('About to remove ' + deletePlan.length + ' snippets from the LOCAL');
console.log('snippets.json file. This does NOT touch your database.\n');
console.log('The following snippets will be removed:');
deletePlan.forEach((r) => {
  console.log('  - [' + r.id + '] ' + (r.title || '(no title)'));
});
console.log('');

// 1) Make a timestamped backup using execFileSync (no shell string concat).
//    We call the platform copy command with arguments passed as an array, so
//    nothing is interpreted by a shell.
const backupPath = SNIPPETS_PATH + '.' + timestamp() + '.bak';
try {
  if (process.platform === 'win32') {
    // Windows: use cmd's COPY. execFileSync passes args safely as an array.
    // /Y suppresses overwrite prompts (the backup name is unique anyway).
    execFileSync('cmd', ['/c', 'copy', '/Y', SNIPPETS_PATH, backupPath], {
      stdio: 'inherit',
    });
  } else {
    // macOS / Linux: use cp.
    execFileSync('cp', [SNIPPETS_PATH, backupPath], { stdio: 'inherit' });
  }
} catch (e) {
  fail('Failed to create backup, aborting before any change: ' + e.message);
}

if (!fs.existsSync(backupPath)) {
  fail('Backup was not created, aborting before any change.');
}
console.log('Backup created: ' + backupPath);

// 2) Build the surviving set = everything NOT in the delete plan.
const deleteIndexes = new Set(deletePlan.map((r) => r.index));
const survivors = snippets.filter((_, i) => !deleteIndexes.has(i));

// 3) Write back in the same shape we loaded (array or wrapped object).
let output;
if (containerKey) {
  output = Object.assign({}, parsed, { [containerKey]: survivors });
} else {
  output = survivors;
}
writeJson(SNIPPETS_PATH, output);

console.log('');
console.log('Done. snippets.json now contains ' + survivors.length + ' snippets ');
console.log('(' + deletePlan.length + ' removed). Original saved at the .bak file above.');
console.log('If anything looks wrong, restore by copying the .bak back over snippets.json.');
