import { expect, test, type Page } from '@playwright/test';
import { setup } from './custom-plan-fixture';
import type { CommunityEntry } from '../lib/api-schema.generated';
const id='00000000-0000-4000-8000-000000000081', revision='00000000-0000-4000-8000-000000000082';
function entry(status: CommunityEntry['status']='in_review'): CommunityEntry {
 return { id, revision_id: revision, name: 'My defensive drill', equipment: 'Bag', notes: 'Keep hands up.', media_id: null, status, submitted_at:'2026-10-11T12:00:00Z', created_at:'2026-10-11T12:00:00Z', reason:null, verified:false, confirmed:false, published:status==='published',has_publication:status==='published', contributor:{username:'fighter',avatar_url:null},media:null,thumbnail:null,audit:[],reports:[],prescription_allowed:false };
}
async function mockCommunity(page: Page, initial: CommunityEntry) {
 let current=initial; const actions:string[]=[];
 await page.route('**/api/community-exercises**',async route=>{
  const req=route.request(), path=new URL(req.url()).pathname, body=req.method()==='GET'?null:req.postDataJSON();
  const json=(value:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
  if(req.method()==='GET' && ['/api/community-exercises','/api/community-exercises/review'].includes(path)) return json({entries:[current],total:1,next_offset:null});
  if(req.method()==='POST' && path.endsWith('/drafts')) { actions.push('draft'); current={...current,...body,status:'private'}; return json(current,201); }
  if(req.method()==='POST' && path.endsWith('/submit')) { expect(body).toEqual({share_rights:true,attribution_consent:true});actions.push('submit');current={...current,status:'in_review'}; }
  if(req.method()==='PUT') { actions.push('edit');current={...current,...body,revision_id:'00000000-0000-4000-8000-000000000083',verified:false,confirmed:false}; }
  if(req.method()==='POST' && path.includes('/review/')) { actions.push(body.action);if(body.action==='dismiss_report'){expect(body.reason).toBe('Outdated report');current={...current,reports:current.reports.map(r=>r.id===body.report_id?{...r,status:'resolved'}:r)};return json(current);}current={...current,verified:true,confirmed:body.action==='confirm'||body.action==='approve',published:body.action==='approve',has_publication:body.action==='approve',status:body.action==='approve'?'published':'in_review'}; }
  if(path.endsWith('/report')) { actions.push('report');return route.fulfill({status:204}); }
  return json(current);
 });
 return actions;
}
test.afterEach(async({page})=>{await page.unrouteAll({behavior:'wait'});});
for(const width of [320,390,1280]) {
 test(`Explicit community consent and public self-directed discovery (${width}px)`,async({page,baseURL})=>{
  await page.setViewportSize({width,height:900});const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  const {saved}=await setup(page,baseURL!);const actions=await mockCommunity(page,entry('private'));
  await page.goto('/plans/custom');await page.getByRole('button',{name:'+ Add Session',exact:true}).click();
  await page.getByRole('button',{name:'Create my exercise',exact:true}).click();await page.getByLabel('Exercise name',{exact:true}).fill('My defensive drill');
  await page.getByRole('button',{name:'Community · Private',exact:true}).click();
  const consent=page.getByRole('dialog',{name:'Community exercise',exact:true});
  await expect(consent.getByRole('button',{name:'Submit for review'})).toBeDisabled();
  await consent.getByRole('checkbox').nth(0).check();await consent.getByRole('checkbox').nth(1).check();
  await consent.getByRole('button',{name:'Submit for review'}).click();await expect(consent.getByText('In review',{exact:true})).toBeVisible();expect(actions).toEqual(['draft','submit']);
  await consent.getByRole('button',{name:'Close',exact:true}).click();await page.getByRole('button',{name:'Add exercise',exact:true}).click();
  await page.getByRole('button',{name:'Save Plan',exact:true}).click();await expect(page).toHaveURL(/custom\?plan=/);
  expect([...saved.values()][0].sessions[0].exercises[0]).toMatchObject({origin:'manual',community_id:id});
  await mockCommunity(page,{...entry('published'),verified:true,confirmed:true});
  await page.getByRole('button',{name:'Add from library',exact:true}).click();await page.getByText('Community exercises',{exact:true}).click();
  await page.getByRole('list',{name:'Community drill results'}).getByRole('button').click();
  const preview=page.getByRole('dialog',{name:'My defensive drill',exact:true});await expect(preview.getByText('Community · Added by @fighter')).toBeVisible();
  await preview.getByRole('button',{name:'Add to Session',exact:true}).click();
  await page.getByRole('button',{name:'Save Plan',exact:true}).click();
  await expect.poll(()=>[...saved.values()][0].sessions[0].exercises.length).toBe(2);
  expect([...saved.values()][0].sessions[0].exercises[1]).toMatchObject({origin:'manual',community_revision_id:revision,media_id:null});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);expect(errors).toEqual([]);
 });
 test(`Admin revision verification and desktop sheet (${width}px)`,async({page,baseURL})=>{
  await page.setViewportSize({width,height:900});await setup(page,baseURL!,'admin');const actions=await mockCommunity(page,entry());
  await page.goto('/admin');await page.getByRole('heading',{name:'Exercise reviews',exact:true}).click();await page.locator('details.admin-queue').filter({has:page.getByRole('heading',{name:'Exercise reviews',exact:true})}).getByRole('button',{name:'Review',exact:true}).click();
  const sheet=page.getByRole('dialog',{name:'My defensive drill',exact:true});await sheet.getByText('Edit exercise',{exact:true}).click();
  await sheet.getByLabel('Exercise name',{exact:true}).fill('Corrected drill');await sheet.getByRole('button',{name:'Save revision',exact:true}).click();
  const edited=page.getByRole('dialog',{name:'Corrected drill',exact:true});await expect(edited.getByRole('button',{name:'Verify exercise',exact:true})).toBeVisible();
  await edited.getByRole('button',{name:'Verify exercise',exact:true}).click();await expect(edited.getByRole('button',{name:'Confirm final revision'})).toBeDisabled();
  await edited.getByRole('checkbox').check();await edited.getByRole('button',{name:'Confirm final revision'}).click();
  await expect(edited.getByRole('button',{name:'Approve and publish'})).toBeDisabled();await edited.getByRole('checkbox').check();await edited.getByRole('button',{name:'Approve and publish'}).click();
  await expect(edited.getByText(/Published/)).toBeVisible();expect(actions).toEqual(['edit','verify','confirm','approve']);
  expect(await edited.evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  if(width===1280){const bounds=await edited.boundingBox();expect(bounds!.width).toBeGreaterThan(600);}
  await page.screenshot({path:`${process.env.TEMP ?? "/tmp"}/unlxck-community-review-${width}.png`});
 });
}

 test('Dismiss a report without removing the published exercise',async({page,baseURL})=>{
  await setup(page,baseURL!,'admin');const published={...entry('published'),verified:true,confirmed:true,reports:[{id:'00000000-0000-4000-8000-000000000084',status:'open',reason:'Old concern'}]};
  const actions=await mockCommunity(page,published);await page.goto('/admin');await page.getByRole('heading',{name:'Exercise reviews',exact:true}).click();
  await page.locator('details.admin-queue').filter({has:page.getByRole('heading',{name:'Exercise reviews',exact:true})}).getByRole('button',{name:'Review',exact:true}).click();
  const sheet=page.getByRole('dialog',{name:published.name,exact:true});await sheet.getByText('Reports (1)',{exact:true}).click();
  await expect(sheet.getByRole('button',{name:'Dismiss report',exact:true})).toBeDisabled();await sheet.getByLabel('Dismissal reason',{exact:true}).fill('Outdated report');
  await sheet.getByRole('button',{name:'Dismiss report',exact:true}).click();await expect(sheet.getByText('· Resolved',{exact:false})).toBeVisible();await expect(sheet.getByText(/Published/)).toBeVisible();expect(actions).toEqual(['dismiss_report']);
 });
