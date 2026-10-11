// Isolated PostgreSQL checks. npm install --prefix <temp> @electric-sql/pglite@0.5.8
// node tools/test_private_media_migration.mjs <temp>
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
const require = createRequire(import.meta.url);
process.on("unhandledRejection", error => { console.error(error.message, error.where ?? ""); process.exit(1); });
process.on("uncaughtException", error => { console.error(error.message, error.where ?? ""); process.exit(1); });
const { PGlite } = await import(pathToFileURL(require.resolve("@electric-sql/pglite", { paths: [process.argv[2]] })).href);
const db = new PGlite();
await db.exec(`
  create role anon; create role authenticated; create role service_role bypassrls;
  create schema auth; create schema storage;
  grant usage on schema auth,storage,public to anon,authenticated,service_role;
  create function auth.uid() returns uuid language sql stable as $$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
  create function public.set_updated_at() returns trigger language plpgsql as $$begin new.updated_at=now(); return new; end$$;
  create table public.profiles(id uuid primary key);
  create table public.custom_training_plans(id uuid primary key default gen_random_uuid(),athlete_id uuid, sessions jsonb);
  create table storage.buckets(id text primary key,name text,public boolean,file_size_limit integer,allowed_mime_types text[]);
  create table storage.objects(id uuid primary key default gen_random_uuid(),bucket_id text,name text,created_at timestamptz default now(),unique(bucket_id,name));
  alter table storage.objects enable row level security;
  grant all on storage.objects to service_role,authenticated,anon;
  grant select on storage.buckets to service_role;
  grant all on public.custom_training_plans to service_role;
  create policy deliberately_broad on storage.objects for all to anon,authenticated using(true) with check(true);
`);
await db.exec(readFileSync("supabase/migrations/20261011203627_private_exercise_media.sql", "utf8"));
await db.exec(readFileSync("supabase/migrations/20261011203631_private_media_retry_cleanup.sql", "utf8"));
const owner = "00000000-0000-4000-8000-000000000001", other = "00000000-0000-4000-8000-000000000002";
await db.query("insert into profiles values($1),($2)", [owner, other]);
let passed = 0;
async function test(name, run) { await run(); console.log(`PASS ${name}`); passed++; }
async function as(role, user) {
  await db.exec(`reset role; set role ${role}`);
  await db.query("select set_config('request.jwt.claim.sub',$1,false)", [user]);
}
async function reserve() {
  await as("service_role", owner);
  return (await db.query("select * from public.reserve_private_video($1,100,'video/mp4')", [owner])).rows[0];
}
const asset = await reserve();
await test("private buckets and five-minute owner lease", async () => {
  assert.equal(asset.athlete_id, owner);
  assert.match(asset.intake_path, new RegExp(`^${owner}/${asset.id}/source$`));
  assert.equal((await db.query("select count(*)::int n from storage.buckets where public")).rows[0].n, 0);
  assert.ok(new Date(asset.upload_expires_at) - new Date(asset.created_at) <= 300001);
});
await test("owner can insert only reserved raw object", async () => {
  await as("authenticated", owner);
  await db.query("insert into storage.objects(bucket_id,name) values('private-demo-intake',$1)", [asset.intake_path]);
  await assert.rejects(db.query("insert into storage.objects(bucket_id,name) values('private-demo-intake','forged/path')"));
  await assert.rejects(db.query("insert into storage.objects(bucket_id,name) values('private-demo-ready','forged/demo.mp4')"));
});
await test("raw and ready bytes cannot be read even with broad preexisting policies", async () => {
  assert.equal((await db.query("select count(*)::int n from storage.objects")).rows[0].n, 0);
  assert.equal((await db.query("delete from storage.objects returning *")).rows.length, 0);
  await as("authenticated", other);
  assert.equal((await db.query("select count(*)::int n from private_video_assets")).rows[0].n, 0);
  await assert.rejects(db.query("insert into storage.objects(bucket_id,name) values('private-demo-intake',$1)", [asset.intake_path]));
});
await test("ordinary users cannot reserve, verify or write media directly", async () => {
  await assert.rejects(db.query("select * from public.reserve_private_video($1,100,'video/mp4')", [other]));
  await assert.rejects(db.query("select public.finish_private_video($1,10,1280,720,'hash')", [asset.id]));
  await assert.rejects(db.query("update private_video_assets set status='verified'"));
  await assert.rejects(db.query("insert into private_exercise_media(athlete_id,provider,video_id,start_s,end_s,made_for_kids) values($1,'youtube','abcdefghijk',0,30,false)", [other]));
});
await test("expired reservations cannot upload", async () => {
  const stale = await reserve();
  await db.query("update private_video_assets set upload_expires_at=now()-interval '1 second' where id=$1", [stale.id]);
  await as("authenticated", owner);
  await assert.rejects(db.query("insert into storage.objects(bucket_id,name) values('private-demo-intake',$1)", [stale.intake_path]));
});
await test("worker claims once and finish creates distinct immutable identity", async () => {
  await as("service_role", owner);
  const claimed = (await db.query("select * from claim_private_video()")).rows;
  assert.equal(claimed.length, 1); assert.equal(claimed[0].id, asset.id);
  assert.equal((await db.query("select * from claim_private_video()")).rows.length, 0);
  await assert.rejects(db.query("select finish_private_video($1,30.1,1280,720,'hash')", [asset.id]));
  await db.query("select finish_private_video($1,30,1280,720,'hash')", [asset.id]);
  const media = (await db.query("select * from private_exercise_media where asset_id=$1", [asset.id])).rows[0];
  assert.notEqual(media.id, media.asset_id); assert.equal(media.video_id, null);
  assert.equal(media.provider, "uploaded"); assert.equal(media.end_s, 30);
  await db.query("select finish_private_video($1,30,1280,720,'hash')", [asset.id]);
  assert.equal((await db.query("select count(*)::int n from private_exercise_media where asset_id=$1", [asset.id])).rows[0].n, 1);
  await assert.rejects(db.query("select finish_private_video($1,10,1280,720,'hash')", [asset.id]));
});
await test("verified raw cleanup never targets the finished rendition", async () => {
  await as("postgres", owner);
  await db.query("update storage.objects set created_at=now()-interval '2 hours' where name=$1", [asset.intake_path]);
  await db.query("insert into storage.objects(bucket_id,name,created_at) values('private-demo-ready',$1,now()-interval '2 hours')", [`${owner}/${asset.id}/demo.mp4`]);
  await as("service_role", owner);
  const candidates = (await db.query("select * from private_demo_orphan_objects()")).rows;
  assert.ok(candidates.some(r => r.name === asset.intake_path));
  assert.ok(!candidates.some(r => r.bucket_id === 'private-demo-ready'));
});
await test("abandoned YouTube clips reclaim quota, retaining saved and fresh previews", async () => {
  await db.query(`insert into private_exercise_media(athlete_id,provider,video_id,end_s,made_for_kids,created_at)
    select $1,'youtube','abcdefghijk',30,false,now()-interval '2 days' from generate_series(1,199)`, [owner]);
  const saved = (await db.query("select id from private_exercise_media where provider='youtube' limit 1")).rows[0];
  await db.query("insert into custom_training_plans(athlete_id,sessions) values($1,$2)", [owner, JSON.stringify([{exercises:[{media_id:saved.id}]}])]);
  const fresh = (await db.query("insert into private_exercise_media(athlete_id,provider,video_id,end_s,made_for_kids) values($1,'youtube','abcdefghijk',30,false) returning id", [other])).rows[0];
  assert.equal((await db.query("select claim_private_media_budget($1) ok", [owner])).rows[0].ok, true);
  assert.equal((await db.query("select count(*)::int n from private_exercise_media where provider='youtube' and athlete_id=$1", [owner])).rows[0].n, 1);
  assert.equal((await db.query("select cleanup_private_youtube_previews(null) n")).rows[0].n, 0);
  assert.equal((await db.query("select id from private_exercise_media where id=$1", [fresh.id])).rows.length, 1);
  await db.query(`insert into private_exercise_media(athlete_id,provider,video_id,end_s,made_for_kids)
    select $1,'youtube','abcdefghijk',30,false from generate_series(1,199)`, [other]);
  assert.equal((await db.query("select claim_private_media_budget($1) ok", [other])).rows[0].ok, false);
  await db.query("update private_exercise_media set created_at=now()-interval '2 days' where athlete_id=$1 and id <> $2", [other,fresh.id]);
  assert.equal((await db.query("select cleanup_private_youtube_previews($1) n", [owner])).rows[0].n, 0);
  assert.equal((await db.query("select claim_private_media_budget($1) ok", [other])).rows[0].ok, true);
  await as("authenticated", other);
  await assert.rejects(db.query("select cleanup_private_youtube_previews(null)"));
  await as("service_role", owner);
});
await test("stale processing leases are recoverable; active retries survive retention", async () => {
  const stalled = await reserve();
  await db.query("insert into storage.objects(bucket_id,name) values('private-demo-intake',$1)", [stalled.intake_path]);
  assert.equal((await db.query("select * from claim_private_video()")).rows[0].id, stalled.id);
  await as("postgres", owner);
  await db.exec("alter table private_video_assets disable trigger private_video_assets_updated");
  await db.query("update private_video_assets set created_at=now()-interval '2 days',updated_at=now()-interval '11 minutes' where id=$1", [stalled.id]);
  await db.exec("alter table private_video_assets enable trigger private_video_assets_updated");
  await as("service_role", owner);
  assert.equal((await db.query("select * from claim_private_video()")).rows[0].id, stalled.id);
  assert.ok(!(await db.query("select * from private_video_cleanup_candidates()")).rows.some(r => r.id === stalled.id));
});
await test("rate limits include parallel API instances through durable reservations", async () => {
  while ((await db.query("select count(*)::int n from private_media_budget where upload")).rows[0].n < 6) await reserve();
  assert.equal((await db.query("select * from reserve_private_video($1,100,'video/mp4')", [owner])).rows.length, 0);
});
await test("saved plan reference retains rendition; unreferenced assets become cleanup candidates", async () => {
  await db.query("update private_video_assets set created_at=now()-interval '8 days' where id=$1", [asset.id]);
  const media = (await db.query("select id from private_exercise_media where asset_id=$1", [asset.id])).rows[0];
  const plan = (await db.query("insert into custom_training_plans(athlete_id,sessions) values($1,$2) returning id", [owner, JSON.stringify([{exercises:[{media_id:media.id}]}])])).rows[0];
  assert.equal((await db.query("select * from private_video_cleanup_candidates()")).rows.some(r => r.id === asset.id), false);
  await db.query("delete from custom_training_plans where id=$1", [plan.id]);
  assert.equal((await db.query("select * from private_video_cleanup_candidates()")).rows.some(r => r.id === asset.id), true);
});
await test("deleted accounts leave storage cleanup candidates", async () => {
  await as("postgres", owner);
  await db.query("update storage.objects set created_at=now()-interval '2 hours' where name=$1", [asset.intake_path]);
  await db.query("delete from profiles where id=$1", [owner]);
  await as("service_role", other);
  assert.equal((await db.query("select * from private_demo_orphan_objects()")).rows[0].name, asset.intake_path);
});
console.log(`${passed} PostgreSQL checks passed`);
await db.close();
