// Run with PGLITE_ROOT pointing at an isolated npm install of @electric-sql/pglite.
// No production database or credentials are used.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";

const require = createRequire(resolve(process.env.PGLITE_ROOT ?? "web", "package.json"));
const { PGlite } = require("@electric-sql/pglite");
const db = new PGlite();
const owner = "00000000-0000-4000-8000-000000000001";
const other = "00000000-0000-4000-8000-000000000002";
const sparring = "00000000-0000-4000-8000-000000000020";
const boxing = "00000000-0000-4000-8000-000000000021";
const othersSparring = "00000000-0000-4000-8000-000000000022";
const secondSparring = "00000000-0000-4000-8000-000000000023";
const migration = (name) => readFile(new URL(`../../supabase/migrations/${name}`, import.meta.url), "utf8");

await db.exec(`
  create role anon; create role authenticated; create role service_role bypassrls;
  create schema auth;
  create function auth.uid() returns uuid language sql as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  grant usage on schema auth to authenticated; grant execute on function auth.uid() to authenticated;
  create table public.profiles (id uuid primary key);
  create table public.plans (id uuid primary key, athlete_id uuid);
  create table public.admin_reviews (id uuid primary key default gen_random_uuid(), athlete_id uuid not null,
    reason text not null, status text not null default 'pending', created_at timestamptz not null default now());
  create function public.set_updated_at() returns trigger language plpgsql as $$ begin new.updated_at = now(); return new; end $$;
  insert into public.profiles values ('${owner}'), ('${other}');
`);
await db.exec(await migration("20261010184612_add_external_training_sessions.sql"));
await db.exec(await migration("20260930141404_add_sparring_logs.sql"));
// A pre-existing timer report survives the migration untouched.
await db.query(`select public.record_sparring_log($1, $2, null)`, [owner, JSON.stringify({
  source: "free", training_day: "2026-10-01", intensity: "light", rounds_completed: 3, head_contact: "none", rocked: false })]);
const link = await migration("20261019120000_link_sparring_detail_to_manual_sessions.sql");
await db.exec(link);
await db.exec(link); // Safe reapplication.

const session = (id, athlete, activity, day = "2026-10-17") => db.query(`insert into public.external_training_sessions
  (id, athlete_id, client_request_id, request_fingerprint, training_day, activity, duration_minutes, effort)
  values ($1,$2,gen_random_uuid(),repeat('a',64),$3,$4,45,'hard')`, [id, athlete, day, activity]);
await session(sparring, owner, "sparring");
await session(boxing, owner, "boxing");
await session(othersSparring, other, "sparring");
await session(secondSparring, owner, "sparring");

const record = async (fields, reason = null) => (await db.query(
  `select public.record_sparring_log($1, $2, $3) as result`,
  [owner, JSON.stringify({ source: "free", training_day: "2026-10-19", intensity: "hard", rounds_completed: 6,
    head_contact: "light", rocked: false, notes: "", ...fields }), reason])).rows[0].result;
const reviews = async () => Number((await db.query(`select count(*) from public.admin_reviews`)).rows[0].count);
const logsFor = async (id) => (await db.query(`select * from public.sparring_logs where external_session_id = $1`, [id])).rows;

// The detail takes the manual session's own day, never the submission day.
const first = await record({ external_session_id: sparring, client_request_id: "00000000-0000-4000-8000-000000000101" });
assert.equal(first.log.training_day, "2026-10-17");
assert.equal(first.review, null);

// A retried request returns the same row and writes nothing new.
const retry = await record({ external_session_id: sparring, client_request_id: "00000000-0000-4000-8000-000000000101", rounds_completed: 9 });
assert.equal(retry.log.id, first.log.id);
assert.equal(retry.log.rounds_completed, 6);
assert.equal((await logsFor(sparring)).length, 1);

// A new report for the same session corrects it in place; a rocked report opens
// exactly one review, and a later correction can never withdraw it.
const rocked = await record({ external_session_id: sparring, client_request_id: "00000000-0000-4000-8000-000000000102", rocked: true, head_contact: "heavy" }, "rocked");
assert.equal(rocked.log.id, first.log.id);
assert.equal(rocked.log.rocked, true);
assert.ok(rocked.review?.id);
assert.equal(rocked.log.admin_review_id, rocked.review.id);
assert.equal(await reviews(), 1);
const rockedRetry = await record({ external_session_id: sparring, client_request_id: "00000000-0000-4000-8000-000000000102", rocked: true }, "rocked");
assert.equal(rockedRetry.review.id, rocked.review.id);
const corrected = await record({ external_session_id: sparring, client_request_id: "00000000-0000-4000-8000-000000000103", rocked: false, head_contact: "none" });
assert.equal(corrected.log.rocked, true);
assert.equal(corrected.review.id, rocked.review.id);
assert.equal(await reviews(), 1);
assert.equal((await logsFor(sparring)).length, 1);

// A genuinely separate sparring session on the same day stays distinct.
const second = await record({ external_session_id: secondSparring, client_request_id: "00000000-0000-4000-8000-000000000104" });
assert.notEqual(second.log.id, first.log.id);

// Only the athlete's own, live, sparring sessions can be linked.
for (const id of [boxing, othersSparring, "00000000-0000-4000-8000-000000000099"]) {
  await assert.rejects(record({ external_session_id: id }), /sparring session not found/);
}
await db.query(`update public.external_training_sessions set deleted_at = now() where id = $1`, [secondSparring]);
await assert.rejects(record({ external_session_id: secondSparring }), /sparring session not found/);
await assert.rejects(db.query(`insert into public.sparring_logs (athlete_id, training_day, source, intensity,
  rounds_completed, head_contact, external_session_id) values ($1,'2026-10-17','free','hard',3,'none',$2)`, [other, sparring]));

// Unlinked timer reports keep their old behaviour, now with retry safety.
const timer = await record({ client_request_id: "00000000-0000-4000-8000-000000000105", rocked: true }, "rocked");
const timerRetry = await record({ client_request_id: "00000000-0000-4000-8000-000000000105", rocked: true }, "rocked");
assert.equal(timerRetry.log.id, timer.log.id);
assert.equal(timerRetry.review.id, timer.review.id);
assert.equal(await reviews(), 2);
assert.equal(timer.log.training_day, "2026-10-19");
const legacy = (await db.query(`select * from public.sparring_logs where training_day = '2026-10-01'`)).rows;
assert.equal(legacy.length, 1);
assert.equal(legacy[0].external_session_id, null);

// Hard-deleting a manual session unlinks, but keeps, its safety evidence.
await db.query(`delete from public.external_training_sessions where id = $1`, [sparring]);
const kept = (await db.query(`select * from public.sparring_logs where id = $1`, [first.log.id])).rows[0];
assert.equal(kept.external_session_id, null);
assert.equal(kept.rocked, true);
assert.equal(kept.athlete_id, owner);

await db.close();
console.log("Sparring detail link: ownership, day, retry, correction, sticky head impact and review passed.");
