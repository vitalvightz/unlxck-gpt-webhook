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
const plan = "00000000-0000-4000-8000-000000000010";
const migration = (name) => readFile(new URL(`../../supabase/migrations/${name}`, import.meta.url), "utf8");

await db.exec(`
  create role anon; create role authenticated; create role service_role bypassrls;
  create schema auth;
  create function auth.uid() returns uuid language sql as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
  create table public.profiles (id uuid primary key);
  create table public.plans (id uuid primary key, athlete_id uuid);
  create function public.is_admin() returns boolean language sql as $$ select false $$;
  create function public.set_updated_at() returns trigger language plpgsql as $$ begin new.updated_at = now(); return new; end $$;
  insert into public.profiles values ('${owner}'), ('${other}');
  insert into public.plans values ('${plan}', '${owner}');
`);
await db.exec(await migration("20260618120000_add_today_checkins_and_completions.sql"));
// An existing planned check-in survives the migration untouched.
await db.query(`insert into public.today_checkins (athlete_id, plan_id, training_day, sleep, body, pain, phase, recommendation_state)
  values ($1, $2, '2026-10-18', 'good', 'normal', 'none', 'SPP', 'train_as_planned')`, [owner, plan]);
const change = await migration("20261019150000_allow_plan_free_today_checkins.sql");
await db.exec(change);
await db.exec(change); // Safe reapplication.

const [legacy] = (await db.query(`select * from public.today_checkins where plan_id = $1`, [plan])).rows;
assert.equal(legacy.phase, "SPP");

const upsert = async (athlete, fields) => (await db.query(`select (public.upsert_plan_free_today_checkin($1, $2)).*`, [athlete, JSON.stringify({
  training_day: "2026-10-19", sleep: "good", body: "normal", pain: "none",
  recommendation_state: "train_as_planned", recommendation_reason: "No warning signs today.",
  recommendation_triggers: ["sparse_history"], ...fields })])).rows[0];

// One plan-free row per athlete-day: a second submission updates it in place.
const first = await upsert(owner, {});
assert.equal(first.plan_id, null);
assert.equal(first.phase, null);
const second = await upsert(owner, { pain: "high", recommendation_state: "pull_back" });
assert.equal(second.id, first.id);
assert.equal(second.pain, "high");
assert.deepEqual(second.recommendation_triggers, ["sparse_history"]);
assert.equal(Number((await db.query(`select count(*) from public.today_checkins where athlete_id = $1 and plan_id is null`, [owner])).rows[0].count), 1);

// Separate days and separate athletes stay separate; a planned row for the same
// day never collides with the plan-free one.
await upsert(owner, { training_day: "2026-10-20" });
await upsert(other, {});
await db.query(`insert into public.today_checkins (athlete_id, plan_id, training_day, sleep, body, pain, phase, recommendation_state)
  values ($1, $2, '2026-10-19', 'good', 'normal', 'none', 'GPP', 'train_as_planned')`, [owner, plan]);
assert.equal(Number((await db.query(`select count(*) from public.today_checkins`)).rows[0].count), 5);

// A raw duplicate plan-free insert is rejected by the partial key.
await assert.rejects(db.query(`insert into public.today_checkins (athlete_id, plan_id, training_day, sleep, body, pain, phase, recommendation_state)
  values ($1, null, '2026-10-19', 'good', 'normal', 'none', null, 'modify')`, [owner]));

// The phase travels with the plan, and only with it.
await assert.rejects(db.query(`insert into public.today_checkins (athlete_id, plan_id, training_day, sleep, body, pain, phase, recommendation_state)
  values ($1, null, '2026-10-21', 'good', 'normal', 'none', 'GPP', 'modify')`, [owner]), /today_checkins_phase_matches_plan/);
await assert.rejects(db.query(`insert into public.today_checkins (athlete_id, plan_id, training_day, sleep, body, pain, phase, recommendation_state)
  values ($1, $2, '2026-10-21', 'good', 'normal', 'none', null, 'modify')`, [owner, plan]), /today_checkins_phase_matches_plan/);
await assert.rejects(upsert(owner, { recommendation_state: "go" }));

// The RPC is backend-only.
assert.equal((await db.query(`select has_function_privilege('authenticated', 'public.upsert_plan_free_today_checkin(uuid, jsonb)', 'execute') as can`)).rows[0].can, false);

await db.close();
console.log("Plan-free today check-ins: legacy preservation, one row per day, no invented phase, backend-only upsert passed.");
