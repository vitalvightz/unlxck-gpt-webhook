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
  create table public.profiles(id uuid primary key,role text default 'athlete',access_status text default 'approved',username text,avatar_url text); grant select on public.profiles to service_role;
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

await db.exec(readFileSync('supabase/migrations/20261011212949_community_exercise_review.sql','utf8'));
const owner='00000000-0000-4000-8000-000000000001', admin='00000000-0000-4000-8000-000000000002', other='00000000-0000-4000-8000-000000000003';
await db.query("insert into profiles(id,role,username,avatar_url) values($1,'athlete','fighter','https://example.com/profile.png'),($2,'admin','admin',null),($3,'athlete','other',null)",[owner,admin,other]);
await db.exec('set role service_role');
let passed=0;
async function test(name,run){await run();console.log(`PASS ${name}`);passed++;}
async function command(actor,action,payload){return (await db.query('select community_command($1,$2,$3) id',[actor,action,JSON.stringify(payload)])).rows[0].id;}
async function detail(actor,id,review=false){return (await db.query('select community_detail($1,$2,$3) entry',[actor,id,review])).rows[0].entry;}
async function list(actor,scope='public'){return (await db.query('select community_list($1,$2) result',[actor,scope])).rows[0].result;}
const clip=(await db.query("insert into private_exercise_media(athlete_id,provider,video_id,start_s,end_s,made_for_kids,created_at) values($1,'youtube','abcdefghijk',10,25,false,now()-interval '2 days') returning id",[owner])).rows[0].id;
let revision=await command(owner,'draft',{name:'Community drill',equipment:'Bag',notes:'Hands up',media_id:clip});
let exercise=(await detail(owner,revision)).id;
const submit={revision_id:revision,share_rights:true,attribution_consent:true};
await test('private by default; ordinary users cannot access review or another draft',async()=>{
  assert.equal((await list(other)).total,0);
  await assert.rejects(detail(other,revision));
  await assert.rejects(list(owner,'review'));
  await assert.rejects(command(other,'approve',{revision_id:revision,final_confirmation:true}));
  await db.exec('set role authenticated');
  await assert.rejects(db.query('select community_command($1,$2,$3)',[owner,'approve',JSON.stringify(submit)]));
  for(const table of ['community_exercises','community_exercise_revisions','community_exercise_audit','community_exercise_reports']) await assert.rejects(db.query(`select * from ${table}`));
  await db.exec('reset role; set role service_role');
});
await test('explicit rights and attribution consent are required',async()=>{
  await assert.rejects(command(owner,'submit',{...submit,share_rights:false}));
  await assert.rejects(command(owner,'submit',{...submit,attribution_consent:false}));
  await command(owner,'submit',submit);
  assert.equal((await detail(owner,revision)).status,'in_review');
  assert.equal((await list(other)).total,0);
});
await test('review retains unused YouTube media and cannot publish without verification and confirmation',async()=>{
  assert.equal((await db.query('select cleanup_private_youtube_previews(null) n')).rows[0].n,0);
  await assert.rejects(command(admin,'approve',{revision_id:revision,final_confirmation:true}));
  await command(admin,'verify',{revision_id:revision,verified_media_id:clip,youtube_id:'abcdefghijk',youtube_verified:true});
  await assert.rejects(command(admin,'confirm',{revision_id:revision,final_confirmation:false}));
  await command(admin,'confirm',{revision_id:revision,final_confirmation:true});
});
await test('admin edits persist as a new revision and invalidate prior video verification',async()=>{
  const previous=revision;
  revision=await command(admin,'edit',{revision_id:revision,name:'Reviewed drill',equipment:'Pads',notes:'Chin down',media_id:clip});
  const current=await detail(admin,revision,true);
  assert.notEqual(revision,previous);assert.equal(current.name,'Reviewed drill');assert.equal(current.equipment,'Pads');assert.equal(current.notes,'Chin down');
  assert.equal(current.verified,false);assert.equal(current.confirmed,false);
  await assert.rejects(command(admin,'approve',{revision_id:previous,final_confirmation:true}));
  await assert.rejects(command(admin,'approve',{revision_id:revision,final_confirmation:true}));
});
await test('only final confirmed revision publishes with live consenting profile attribution',async()=>{
  await command(admin,'verify',{revision_id:revision,verified_media_id:clip,youtube_id:'abcdefghijk',youtube_verified:true});
  await command(admin,'confirm',{revision_id:revision,final_confirmation:true});
  await command(admin,'approve',{revision_id:revision,final_confirmation:true,username:'forged',avatar_url:'https://evil.test'});
  const found=await list(other);assert.equal(found.total,1);assert.equal(found.entries[0].contributor.username,'fighter');assert.equal(found.entries[0].contributor.avatar_url,'https://example.com/profile.png');
  await db.exec('reset role');await db.query("update profiles set username='updated',avatar_url=null where id=$1",[owner]);await db.exec('set role service_role');
  assert.equal((await list(other)).entries[0].contributor.username,'updated');
  assert.equal((await list(other)).entries[0].contributor.avatar_url,null);
});
const plan=(await db.query('insert into custom_training_plans(athlete_id,sessions) values($1,$2) returning id',[other,JSON.stringify([{exercises:[{community_revision_id:revision}]}])])).rows[0];
await test('new public edits preserve approved media and saved snapshots until replacement approval',async()=>{
  const next=await command(admin,'edit',{revision_id:revision,name:'New revision',equipment:null,notes:null,media_id:clip});
  assert.equal((await list(other)).entries[0].revision_id,revision);
  assert.equal((await detail(other,revision)).name,'Reviewed drill');
  assert.equal((await detail(admin,next,true)).verified,false);
  await command(admin,'request_changes',{revision_id:next,reason:'Adjust demonstration'});
  assert.equal((await detail(owner,next)).reason,'Adjust demonstration');
  await command(owner,'submit',{revision_id:next,share_rights:true,attribution_consent:true});
  await command(admin,'reject',{revision_id:next,reason:'Wrong movement'});
  assert.equal((await detail(owner,next)).status,'rejected');
});
await test('reports enter moderation, removal hides discovery but retains saved private use',async()=>{
  await command(other,'report',{revision_id:revision,reason:'Video mismatch'});
  assert.equal((await detail(admin,revision,true)).reports[0].reason,'Video mismatch');
  await assert.rejects(command(owner,'remove',{revision_id:revision,reason:'unauthorized'}));
  await command(admin,'remove',{revision_id:revision,reason:'Review video'});
  assert.equal((await list(other)).total,0);
  assert.equal((await detail(other,revision)).name,'Reviewed drill');
  await assert.rejects(detail(owner,revision,true));
  await assert.rejects(db.query('insert into custom_training_plans(athlete_id,sessions) values($1,$2)',[other,JSON.stringify([{exercises:[{community_revision_id:revision}]}]) ]));
  await db.query('update custom_training_plans set sessions=sessions where id=$1',[plan.id]);
});
await test('withdrawal clears credit and publication while preserving owner exercise and audits',async()=>{
  await command(owner,'withdraw',{revision_id:revision});
  assert.equal((await list(other)).total,0);
  const current=(await list(owner,'mine')).entries[0];assert.equal(current.status,'private');assert.equal(current.contributor,null);
  const reviewed=await detail(admin,current.revision_id,true);
  assert.ok(reviewed.audit.some(x=>x.action==='edit'));assert.ok(reviewed.audit.some(x=>x.action==='approve'));assert.ok(reviewed.audit.some(x=>x.action==='withdraw'));
});
await test('processed uploaded media stays retained through review and stale approval cannot verify a replacement',async()=>{
  const asset=(await db.query("select * from reserve_private_video($1,100,'video/mp4')",[owner])).rows[0];
  await db.query("insert into storage.objects(bucket_id,name) values('private-demo-intake',$1)",[asset.intake_path]);
  await db.query('select * from claim_private_video()');await db.query("select finish_private_video($1,12,1280,720,'proof')",[asset.id]);
  const media=(await db.query('select id from private_exercise_media where asset_id=$1',[asset.id])).rows[0].id;
  let id=await command(owner,'draft',{name:'Uploaded drill',media_id:media});await command(owner,'submit',{revision_id:id,share_rights:true,attribution_consent:true});
  await db.query("update private_video_assets set created_at=now()-interval '8 days' where id=$1",[asset.id]);
  assert.ok(!(await db.query('select * from private_video_cleanup_candidates()')).rows.some(x=>x.id===asset.id));
  await assert.rejects(command(admin,'verify',{revision_id:id,verified_media_id:media,sha256:'wrong'}));
  await command(admin,'verify',{revision_id:id,verified_media_id:media,sha256:'proof'});await command(admin,'confirm',{revision_id:id,final_confirmation:true});
  id=await command(admin,'edit',{revision_id:id,name:'Uploaded drill',media_id:clip});
  await assert.rejects(command(admin,'approve',{revision_id:id,final_confirmation:true}));
});
await test('account deletion removes public attribution and media identity safely',async()=>{
  await db.exec('reset role');await db.query('delete from profiles where id=$1',[owner]);await db.exec('set role service_role');
  assert.equal((await list(other)).total,0);
  assert.equal((await detail(other,revision)).contributor,null);
});
console.log(`${passed} community PostgreSQL checks passed`);
await db.close();
