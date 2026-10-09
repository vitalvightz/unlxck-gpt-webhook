// Run against isolated WASM PostgreSQL, never a linked Supabase project.
// npm install --prefix <temporary-directory> @electric-sql/pglite@0.5.8
// node tools/test_rehab_migration.mjs <temporary-directory>
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";

process.on("uncaughtException", error => { console.error(error.message, error.where ?? ""); process.exit(1); });
process.on("unhandledRejection", error => { console.error(error.message, error.where ?? ""); process.exit(1); });

const require = createRequire(import.meta.url);
const { PGlite } = await import(pathToFileURL(require.resolve("@electric-sql/pglite", { paths: [process.argv[2]] })).href);
const db = new PGlite();
const schema = readFileSync("supabase/schema.sql", "utf8");
const table = name => schema.match(new RegExp(`create table if not exists public\\.${name} \\([\\s\\S]*?\\n\\);`))[0];
await db.exec(`create role anon; create role authenticated; create role service_role bypassrls;
  create schema auth; grant usage on schema auth, public to authenticated, service_role;
  create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub', true),'')::uuid$$;
  create table public.profiles(id uuid primary key); create table public.plans(id uuid primary key);
  ${schema.match(/create or replace function public\.injury_flags_infection_signs_valid[\s\S]*?\$\$;/)[0]}
  ${table("injury_flags")}
  alter table injury_flags add column episode_id uuid not null default gen_random_uuid(), add column body_region text, add column side text not null default 'unknown';
  create unique index injury_flags_episode_owner_idx on public.injury_flags(id,athlete_id,episode_id);
  ${table("today_checkins")} ${table("session_completions")} ${table("rehab_exposures")}`);
const migration = readFileSync("supabase/migrations/20260930173118_injury_episode_prescription_history.sql", "utf8");
await db.exec(readFileSync("supabase/migrations/20260820170000_add_rehab_response_group_identity.sql", "utf8"));
await db.exec(migration);
const profileMigration = readFileSync("supabase/migrations/20261002234842_pathway_profile_unknown_side.sql", "utf8");
const nullDoseMigration = readFileSync("supabase/migrations/20261009100907_rehab_exposure_json_null_prescribed_dose.sql", "utf8");
await db.exec(profileMigration);
await db.exec(profileMigration); // CREATE OR REPLACE preserves the existing grants and observations.
await db.exec(nullDoseMigration);
const athlete = "00000000-0000-4000-8000-000000000001";
const other = "00000000-0000-4000-8000-000000000002";
const plan = "00000000-0000-4000-8000-000000000003";
const secondPlan = "00000000-0000-4000-8000-000000000004";
const injury = "00000000-0000-4000-8000-000000000005";
const episode = "00000000-0000-4000-8000-000000000006";
await db.query("insert into profiles values ($1),($2)", [athlete, other]);
await db.query("insert into plans values ($1),($2)", [plan, secondPlan]);
await db.query("insert into injury_flags(id,athlete_id,description,body_region,side,episode_id) values($1,$2,'ankle sprain','ankle','left',$3)", [injury, athlete, episode]);
let passed = 0;
async function test(name, fn) { await fn(); console.log(`PASS ${name}`); passed++; }
async function rejects(fn, text) { await assert.rejects(fn, error => error.message.includes(text)); }
async function snapshot(day, session, selectedPlan=plan, gap=2) {
  let checkin = (await db.query("select * from today_checkins where athlete_id=$1 and plan_id=$2 and training_day=$3", [athlete, selectedPlan, day])).rows[0];
  if (!checkin) checkin = (await db.query("insert into today_checkins(athlete_id,plan_id,training_day,sleep,body,pain,phase,recommendation_state) values($1,$2,$3,'good','sharp','none','GPP','train_as_planned') returning *", [athlete, selectedPlan, day])).rows[0];
  const flag = (await db.query("select * from injury_flags where id=$1", [injury])).rows[0];
  const events = (await db.query("select id from injury_episode_events where athlete_id=$1 and event_type in ('injury_checkin','delayed_rehab_response') order by created_at desc,id desc limit 1", [athlete])).rows;
  const exposures = (await db.query("select id from rehab_exposures where athlete_id=$1 order by created_at desc,id desc limit 1", [athlete])).rows;
  return { plan_id: selectedPlan, training_day: day, revision: "a".repeat(64), allocation_limit: 2,
    readiness_context: { id: checkin.id, updated_at: checkin.updated_at.toISOString() },
    injury_context: [{ id: injury, episode_id: flag.episode_id, updated_at: flag.updated_at.toISOString() }],
    evidence_context: {event_id: events[0]?.id ?? null, exposure_id: exposures[0]?.id ?? null},
    session: { session_id: session, blocks: [{ block_type: "rehab", policy_id: "ankle_sprain", rehab_drill_id: "ankle_sprain_heel_lowering",
      injury_id: injury, injury_episode_id: flag.episode_id, minimum_gap_days: gap }] } };
}
async function start(snap, status="started") {
  return db.query(`insert into session_completions(athlete_id,plan_id,session_id,training_day,status,prescription_snapshot)
    values($1,$2,$3,$4,$5,$6::jsonb) on conflict(athlete_id,session_id,training_day) do update
    set status=excluded.status,prescription_snapshot=excluded.prescription_snapshot returning *`,
    [athlete,snap.plan_id,snap.session.session_id,snap.training_day,status,JSON.stringify(snap)]);
}
await test("pending migration can be reapplied without losing history", async () => {
  const before = (await db.query("select count(*)::int n from injury_episode_events")).rows[0].n;
  await db.exec(migration);
  await db.exec(profileMigration);
  await db.exec(nullDoseMigration);
  assert.equal((await db.query("select count(*)::int n from injury_episode_events")).rows[0].n,before);
});
const first = await snapshot("2026-09-30", "training-first");
await test("start and retry retain one accepted snapshot", async () => {
  await start(first); await start(first);
  assert.equal((await db.query("select count(*)::int n from session_completions")).rows[0].n,1);
});
await test("different session and plan cannot reuse daily episode", async () => {
  await rejects(() => start({...first, plan_id:secondPlan, session:{...first.session,session_id:"standalone"}}), "prescription_revision_conflict");
  const duplicate = await snapshot("2026-09-30", "standalone", secondPlan);
  await rejects(() => start(duplicate), "rehab_daily_allocation_conflict");
});
await test("accepted snapshots cannot be edited or terminal credit erased", async () => {
  await rejects(() => start({...first, revision:"b".repeat(64)}), "prescription_revision_conflict");
  await start(first,"done");
  await rejects(() => start(first,"not_started"), "rehab_exposure_cannot_be_reset");
});
await test("alternate day gap includes modified work and survives plan changes", async () => {
  const next = await snapshot("2026-10-01","next-day",secondPlan,1);
  await rejects(() => start(next), "rehab_daily_allocation_conflict");
  await start(await snapshot("2026-10-02","two-days",secondPlan),"modified");
  await start(await snapshot("2026-10-08","missed-days"));
});
await test("skipped sessions create no exercise credit", async () => {
  await start(await snapshot("2026-10-12","skip"),"skipped");
  await start(await snapshot("2026-10-12","actual"));
});
await test("owner-only event reads and backend-only writes", async () => {
  await db.exec(`set role authenticated; set request.jwt.claim.sub='${other}';`);
  assert.equal((await db.query("select * from injury_episode_events")).rows.length,0);
  await rejects(() => db.query("insert into injury_episode_events(id) values(gen_random_uuid())"), "permission denied");
  await db.exec(`set request.jwt.claim.sub='${athlete}';`);
  assert.ok((await db.query("select * from injury_episode_events")).rows.length > 0);
  await db.exec("reset role;");
});
await test("optional clearance never gates an otherwise eligible start", async () => {
  const stale = await snapshot("2026-10-16","stale-feedback");
  const report = {id:"00000000-0000-4000-8000-000000000020",injury_id:injury,injury_episode_id:episode,
    event_type:"clinician_clearance_report",payload:{source:"athlete_reported",externally_verified:false,scopes:["rehab"]}};
  await db.query("select public.record_injury_episode_event($1,$2::jsonb)",[athlete,JSON.stringify(report)]);
  await start(stale);
});
const exposure = {exposure_id:"00000000-0000-4000-8000-000000000021",response_group_id:"00000000-0000-4000-8000-000000000023",injury_id:injury,injury_episode_id:episode,
  drill_id:"ankle_sprain_heel_lowering",body_region:"ankle",side:"left",demand:{target_regions:["ankle"],load:"low",impact:"none",velocity:"low"},
  dose_completed:{completion_state:"performed_amount_unknown"},response:{during_response:"same",next_day_response:"not_yet_known"},
  occurred_at:"2026-09-30T12:00:00Z",provenance:{source:"athlete_logged_rehab",recorded_at:"2026-09-30T12:30:00Z"}};
await test("exposure and delayed feedback are immutable and idempotent", async () => {
  await db.query("select record_rehab_exposure($1,$2::jsonb)",[athlete,JSON.stringify(exposure)]);
  await db.query("select record_rehab_exposure($1,$2::jsonb)",[athlete,JSON.stringify(exposure)]);
  const stale = await snapshot("2026-10-20","delayed-stale");
  const observation = {id:"00000000-0000-4000-8000-000000000022",injury_id:injury,injury_episode_id:episode,event_type:"delayed_rehab_response",
    payload:{exposure_id:exposure.exposure_id,response:"worse"}};
  await db.query("select record_injury_episode_event($1,$2::jsonb)",[athlete,JSON.stringify(observation)]);
  await db.query("select record_injury_episode_event($1,$2::jsonb)",[athlete,JSON.stringify(observation)]);
  await rejects(() => start(stale),"prescription_revision_conflict");
  assert.deepEqual((await db.query("select event_json from rehab_exposures where id=$1",[exposure.exposure_id])).rows[0].event_json,exposure);
});
await test("an explicit null prescribed dose persists as SQL null", async () => {
  const undosed = {...exposure,exposure_id:"00000000-0000-4000-8000-000000000024",response_group_id:"00000000-0000-4000-8000-000000000025",prescribed_dose:null};
  await db.query("select record_rehab_exposure($1,$2::jsonb)",[athlete,JSON.stringify(undosed)]);
  assert.equal((await db.query("select prescribed_dose from rehab_exposures where id=$1",[undosed.exposure_id])).rows[0].prescribed_dose,null);
});
await test("reopening isolates claims and preserves historical observations", async () => {
  const old = (await db.query("select prescription_snapshot from session_completions where session_id='training-first'")).rows[0].prescription_snapshot;
  await db.query("update injury_flags set episode_id=gen_random_uuid(),updated_at=now() where id=$1",[injury]);
  await start(await snapshot("2026-09-30","reopened"));
  assert.deepEqual((await db.query("select prescription_snapshot from session_completions where session_id='training-first'")).rows[0].prescription_snapshot,old);
  assert.ok((await db.query("select * from injury_episode_events where injury_episode_id=$1",[episode])).rows.length > 0);
  assert.equal((await db.query("select injury_episode_id from rehab_exposures where id=$1",[exposure.exposure_id])).rows[0].injury_episode_id,episode);
});
await test("region-wide baseline feedback keeps unknown side only for frozen work", async () => {
  const chest = "00000000-0000-4000-8000-000000000030", chestEpisode = "00000000-0000-4000-8000-000000000031";
  await db.query("insert into injury_flags(id,athlete_id,description,body_region,side,episode_id) values($1,$2,'chest strain','chest','unknown',$3)",[chest,athlete,chestEpisode]);
  const snap = await snapshot("2026-10-25","chest-guidance");
  const flag = (await db.query("select * from injury_flags where id=$1",[chest])).rows[0];
  snap.injury_context.push({id:chest,episode_id:chestEpisode,updated_at:flag.updated_at.toISOString()});
  snap.session.blocks = [{block_type:"rehab",policy_id:"chest_strain",injury_id:chest,injury_episode_id:chestEpisode,
    rehab_drill_id:"chest_strain_recovery_support",minimum_gap_days:1,drill_snapshot:{rehab_stage:"calm",laterality_applicability:"not_applicable"}}];
  await start(snap,"done");
  const report = {...exposure,exposure_id:"00000000-0000-4000-8000-000000000032",response_group_id:"00000000-0000-4000-8000-000000000033",injury_id:chest,injury_episode_id:chestEpisode,
    drill_id:"chest_strain_recovery_support",body_region:"chest",side:"unknown",demand:{target_regions:["chest"],load:"minimal",impact:"none",velocity:"low"},
    provenance:{...exposure.provenance,prescription_revision:snap.revision,policy_id:"chest_strain",rehab_stage:"calm"}};
  await db.query("select record_rehab_exposure($1,$2::jsonb)",[athlete,JSON.stringify(report)]);
  assert.notEqual(report.response_group_id, exposure.response_group_id);
  for (const side of ["", "  ", "unknown"]) {
    await db.query("update injury_flags set side=$1 where id=$2", [side, chest]);
    await db.query("select record_rehab_exposure($1,$2::jsonb)", [athlete, JSON.stringify(report)]);
  }
  await rejects(() => db.query("select record_rehab_exposure($1,$2::jsonb)",[athlete,JSON.stringify({...report,drill_id:"unattributed_legacy"})]),"exposure does not match");
});
await test("a full rehab allocation does not prohibit training with no rehab", async () => {
  const snap = await snapshot("2026-10-26","two-injuries");
  const flag = (await db.query("select * from injury_flags where body_region='chest'")).rows[0];
  snap.injury_context.push({id:flag.id,episode_id:flag.episode_id,updated_at:flag.updated_at.toISOString()});
  snap.session.blocks.push({block_type:"rehab",policy_id:"chest_strain",injury_id:flag.id,injury_episode_id:flag.episode_id,
    rehab_drill_id:"chest_strain_recovery_support",minimum_gap_days:1});
  await start(snap,"done");
  const normal = await snapshot("2026-10-26","normal-training");
  normal.injury_context = snap.injury_context;
  normal.session.blocks = [];
  normal.allocation_limit = 1;
  await start(normal);
});
const guidanceProfiles = ["hamstring", "calf", "groin", "quads", "future_region"].map(region => [region, "strain"]);
guidanceProfiles.push(["wrist", "sprain"], ["ankle", "instability"], ["achilles", "tendonitis"], ["wrist", "tendonitis"]);
guidanceProfiles.push(...["shoulder", "hip", "ankle", "elbow", "wrist"].map(region => [region, "impingement"]));
guidanceProfiles.push(...["toe", "fingers", "elbow", "wrist", "hand", "shoulder"].map(region => [region, "hyperextension"]));
guidanceProfiles.push(...["heel", "shin", "quads", "biceps", "triceps", "forearm", "shoulder", "elbow", "wrist", "hand", "fingers"].map(region => [region, "contusion"]));
guidanceProfiles.push(...[["shoulder", "pain"], ["elbow", "pain"], ["wrist", "pain"], ["hand", "pain"], ["fingers", "pain"], ["knee", "pain"], ["hip", "pain"], ["lower_back", "pain"], ["neck", "stiffness"], ["elbow", "stiffness"], ["wrist", "stiffness"], ["lower_back", "stiffness"], ["neck", "tightness"], ["shoulder", "tightness"], ["neck", "soreness"], ["shoulder", "soreness"]]);
for (const [index, [region, kind]] of guidanceProfiles.entries()) {
  await test(`${region}_${kind}: frozen profile guidance accepts unknown side with exact provenance`, async () => {
    const id = `00000000-0000-4000-8000-${String(100 + index * 4).padStart(12, "0")}`;
    const ep = `00000000-0000-4000-8000-${String(101 + index * 4).padStart(12, "0")}`;
    const eventId = `00000000-0000-4000-8000-${String(102 + index * 4).padStart(12, "0")}`;
    const groupId = `00000000-0000-4000-8000-${String(103 + index * 4).padStart(12, "0")}`;
    await db.query("insert into injury_flags(id,athlete_id,description,body_region,side,episode_id) values($1,$2,$3,$4,'unknown',$5)",
      [id, athlete, `${region} ${kind}`, region, ep]);
    const trainingDay = new Date(Date.UTC(2026, 10, index + 1)).toISOString().slice(0, 10);
    const snap = await snapshot(trainingDay, `${region}-${kind}-guidance`);
    snap.injury_context = (await db.query("select * from injury_flags where athlete_id=$1 and status in ('open','monitoring')", [athlete])).rows
      .map(flag => ({id:flag.id, episode_id:flag.episode_id, updated_at:flag.updated_at.toISOString()}));
    const policy = `${region}_${kind}`, drill = `${policy}_recovery_support`;
    snap.session.blocks = [{block_type:"rehab", policy_id:policy, injury_id:id, injury_episode_id:ep,
      rehab_drill_id:drill, minimum_gap_days:1, drill_snapshot:{rehab_stage:"calm",laterality_applicability:"not_applicable"}}];
    await start(snap, "done");
    const report = {...exposure,exposure_id:eventId,response_group_id:groupId,injury_id:id,injury_episode_id:ep,
      drill_id:drill,body_region:region,side:"unknown",demand:{target_regions:[region],load:"minimal",impact:"none",velocity:"low"},
      provenance:{...exposure.provenance,prescription_revision:snap.revision,policy_id:policy,rehab_stage:"calm"}};
    await db.query("select record_rehab_exposure($1,$2::jsonb)", [athlete, JSON.stringify(report)]);
    await db.query("select record_rehab_exposure($1,$2::jsonb)", [athlete, JSON.stringify(report)]);
    assert.equal((await db.query("select count(*)::int n from rehab_exposures where id=$1",[eventId])).rows[0].n, 1);
    for (const invalid of [
      {...report,drill_id:"legacy_work"}, {...report,body_region:"chest"},
      {...report,provenance:{...report.provenance,policy_id:"other_profile"}},
      {...report,provenance:{...report.provenance,rehab_stage:"load"}},
      {...report,provenance:{...report.provenance,prescription_revision:"b".repeat(64)}},
    ]) {
      await rejects(() => db.query("select record_rehab_exposure($1,$2::jsonb)", [athlete,JSON.stringify(invalid)]),"exposure does not match");
    }
    await rejects(() => db.query("select record_rehab_exposure($1,$2::jsonb)", [other,JSON.stringify(report)]),"injury not found");
  });
}
console.log(`${passed} database acceptance checks passed (single PostgreSQL connection; advisory locking inspected separately).`);
await db.close();
