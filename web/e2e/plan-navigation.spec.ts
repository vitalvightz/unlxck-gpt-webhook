import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { setup } from './custom-plan-fixture';
import coaching from '../../tests/fixtures/concise_coaching/october_11_15.json';
import type { PlanDetail, StructuredPlan } from '../lib/types';
const id = '00000000-0000-4000-8000-000000000002';
for (const custom of [false, true])
    for (const width of [320, 430, 1280])
        test(`${custom ? "Self-created" : "Fight camp"}: Plan → calendar → session → exercise (${width}px)`, async ({ page, baseURL }) => {
            await page.setViewportSize({ width, height: 932 });
            await page.clock.install({ time: new Date('2026-10-13T12:00:00Z') });
            await setup(page, baseURL!);
            const errors: string[] = [];
            page.on('pageerror', e => errors.push(e.message));
            const source = coaching[0].card.weeks[0];
            const plan = { ...coaching[0].card, plan_metadata: { title: 'Fight camp', plan_type: 'fight_camp' }, weeks: [{ week_index: 1, phase_label: 'GPP', days: [{ date: '2026-10-06', sessions: [] }] }, { ...source, week_index: 2, phase_label: 'GPP', start_date: '2026-10-12', end_date: '2026-10-18', days: [source.days[0], { date: '2026-10-14', day_type: 'rest', sessions: [] }, source.days[1]] }], red_flag_rules: [{ severity: 'red', display_text: 'Chest pain or unusual breathlessness stops training.' }] } as unknown as StructuredPlan;
            let detail = { plan_id: id, athlete_id: '00000000-0000-4000-8000-000000000001', full_name: 'Carlos', status: 'ready', activation_state: 'active', plan_name: '', fight_date: '2026-11-14', created_at: '2026-10-01T12:00:00Z', technical_style: ['boxing'], advisories: [], structured_card_state: { state: 'live', reasons: [] }, schedule_context: { schedule_mode: 'event_countdown', projection_status: 'not_required', current_training_day: '2026-10-13', plan_start_day: '2026-10-01' }, outputs: { plan_text: '# Released fight camp', structured_plan: plan, exercise_media: { 'exercise:jump-squat': { provider: 'youtube', video_id: 'testVideo01', start_s: 0, end_s: 10, source: 'curated' } } } } as unknown as PlanDetail;
            if (custom) {
                detail = { ...detail, custom_plan_id: 'custom-review-plan', plan_name: 'Weekly strength', fight_date: '', outputs: { ...detail.outputs, structured_plan: { ...plan, plan_metadata: { ...plan.plan_metadata, prescription_source: 'athlete' } } }, schedule_context: { ...detail.schedule_context!, schedule_mode: 'open_recurring', projection_status: 'projected', current_week_number: 2, block_number: 1 } };
            }
            const session = plan.weeks![1].days![0].sessions![0];
            const writes: unknown[] = [];
            const starts: Record<string, unknown>[] = [];
            let completionStatus = "not_started";
            await page.route('**/api/plans/**', async (route) => {
                const request = route.request(), url = new URL(request.url());
                const json = (body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
                if (url.pathname.endsWith('/completions'))
                    return json({ completions: completionStatus === 'started' ? [{ training_day: '2026-10-13', session_id: session.session_id, status: 'started' }] : [], current_training_day: '2026-10-13' });
                if (url.pathname.endsWith('/exercise-changes') && request.method() === 'POST') {
                    const body = request.postDataJSON();
                    writes.push(body);
                    const changed = structuredClone(session);
                    changed.blocks![1].sets = body.dose?.sets ?? 4;
                    detail = structuredClone(detail);
                    detail.outputs.structured_plan!.weeks![1].days![0].sessions![0] = changed;
                    return json({ id: 'change-1', session: changed });
                }
                if (url.pathname.endsWith('/alternatives'))
                    return json({ alternatives: [], scopes: ['occurrence'], more_available: false });
                if (url.pathname.endsWith('/active') || url.pathname.endsWith(id))
                    return json(detail);
                return json([]);
            });
            await page.route('**/api/today', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ active_plan: { id, fight_date: detail.fight_date }, risk_watch: [], week_summary: {}, quick_actions: [], open_injuries: [], warnings: [], checkin: { submitted: true }, today: { training_day: '2026-10-13', recommendation_state: 'train_as_planned', completion_status: completionStatus, session_scope: 'today', session_label: 'Strength', decision_tier: 'green', warnings: [], next_session: { session_id: session.session_id, session_relation: 'today', calendar_date: '2026-10-13', title: 'Strength', session_type: 'strength' } } }) }));
            await page.route('**/api/today/session-completion', route => { const body = route.request().postDataJSON(); starts.push(body); completionStatus = body.status; return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ completion: { id: 'completion-1', status: body.status }, rehab_response_prompts: [] }) }); });
            await page.route('**/api/today/exercise-logs?*', route => route.fulfill({
                status: 200, contentType: 'application/json',
                body: JSON.stringify({ logs: [], recent_loads: [], recent_performances: [] }),
            }));
            await page.route('https://i.ytimg.com/**', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#24292f"/><text x="320" y="180" text-anchor="middle" fill="#adb3bd" font-size="24">Demonstration fixture</text></svg>' }));
            await page.goto(`/plans/${id}`);
            await expect(page.getByRole('heading', { name: 'Your Plan', exact: true })).toBeVisible();
            await expect(page.locator('.cm-week-phase-progress')).toContainText(custom ? 'Block 1' : 'General prep');
            await expect(page.locator('.cm-week-phase-progress')).not.toContainText('Specific prep');
            if (process.env.UNLXCK_SCREENSHOTS)
                await page.screenshot({ style: "nextjs-portal { display: none; }", animations: "disabled", path: `${process.env.UNLXCK_SCREENSHOTS}/plan-initial-${width}.png` });
            expect(await page.locator('iframe, video').count()).toBe(0);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.getByRole('button', { name: 'Calendar', exact: true }).click();
            await expect(page.getByRole('navigation', { name: 'Selected week calendar' })).toBeVisible();
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            if (process.env.UNLXCK_SCREENSHOTS)
                await page.screenshot({ style: "nextjs-portal { display: none; }", animations: "disabled", path: `${process.env.UNLXCK_SCREENSHOTS}/calendar-${width}.png` });
            await page.getByRole('button', { name: /14 Oct.*Recovery/ }).click();
            await expect(page.locator('.cm-session-link')).toHaveCount(0);
            await page.getByRole('button', { name: 'List', exact: true }).click();
            const management = page.locator('.plan-detail-hero .plan-action-menu > summary');
            await management.click();
            await expect(page.locator('.plan-detail-hero').getByRole('link', { name: 'All plans', exact: true })).toBeVisible();
            await expect(page.locator('.plan-detail-hero').getByRole('button', { name: 'Rename', exact: true })).toBeVisible();
            if (custom) {
                const editPlan = page.locator('.plan-detail-hero').getByRole('link', { name: 'Edit Plan', exact: true });
                await expect(editPlan).toBeVisible();
                await expect(editPlan).toHaveAttribute('href', '/plans/custom?plan=custom-review-plan');
            }
            await management.click();
            const link = page.locator('.cm-session-link').first();
            await link.scrollIntoViewIfNeeded();
            const scroll = await page.evaluate(() => scrollY);
            await link.click();
            const screen = page.locator('.cm-session-screen');
            await expect(screen.getByRole('heading', { name: 'Exercises', exact: true })).toBeVisible();
            await expect(screen.locator('.ex-row')).toHaveCount(3);
            await expect(screen.getByText('Exercise menus: edit, replace or remove.')).toHaveCount(0);
            await expect(screen.locator('.ex-row-thumb .ex-demo-play-glyph')).toHaveCount(0);
            if (process.env.UNLXCK_SCREENSHOTS)
                await page.screenshot({ style: "nextjs-portal { display: none; }", animations: "disabled", path: `${process.env.UNLXCK_SCREENSHOTS}/session-initial-${width}.png` });
            expect((await new AxeBuilder({ page }).include('.cm-session-screen').analyze()).violations).toEqual([]);
            await screen.getByRole('button', { name: /^Jump Squat/ }).click();
            const exercise = page.locator('.cm-exercise-screen');
            await expect(exercise.getByRole('region', { name: 'Demo video' })).toBeVisible();
            await expect(exercise.getByRole('button', { name: 'Play Jump Squat demo' })).toBeVisible();
            await expect(exercise.locator('.ex-detail-prescription')).toHaveCount(1);
            await expect(exercise.getByText('Drive with hips, extend through the toes and land quietly.', { exact: true })).toBeVisible();
            if (process.env.UNLXCK_SCREENSHOTS)
                await page.screenshot({ style: "nextjs-portal { display: none; }", animations: "disabled", path: `${process.env.UNLXCK_SCREENSHOTS}/exercise-initial-${width}.png` });
            expect((await new AxeBuilder({ page }).include('.cm-exercise-screen').analyze()).violations).toEqual([]);
            await exercise.getByRole('button', { name: 'Edit prescription', exact: true }).click();
            const edit = page.getByRole('dialog', { name: 'Edit Jump Squat', exact: true });
            await edit.getByLabel('Sets', { exact: true }).fill('3');
            await edit.getByRole('button', { name: 'Save changes', exact: true }).click();
            await expect(edit).toHaveCount(0);
            expect(writes.length).toBe(1);
            await expect(exercise.locator('.ex-detail-prescription')).toContainText('3');
            await exercise.getByRole('button', { name: 'Replace exercise', exact: true }).click();
            await expect(page.getByRole('dialog', { name: 'Swap Jump Squat', exact: true })).toBeVisible();
            await page.keyboard.press('Escape');
            if (process.env.UNLXCK_SCREENSHOTS)
                await page.screenshot({ style: "nextjs-portal { display: none; }", animations: "disabled", path: `${process.env.UNLXCK_SCREENSHOTS}/exercise-${width}.png` });
            await page.getByRole('button', { name: 'Back to session', exact: true }).click();
            if (process.env.UNLXCK_SCREENSHOTS)
                await page.screenshot({ style: "nextjs-portal { display: none; }", animations: "disabled", path: `${process.env.UNLXCK_SCREENSHOTS}/session-${width}.png` });
            await expect(screen.getByRole('link', { name: 'Open Today' })).toHaveCount(0);
            await expect(screen.locator('.today-session-controls')).toBeVisible();
            await screen.getByRole('button', { name: 'Start session', exact: true }).click();
            await expect(page.locator('.st-root')).toBeVisible();
            expect(starts[0]?.status).toBe('started');
            expect(starts[0]?.session_id).toBe(session.session_id);
            expect(page.url()).toContain(`/plans/${id}`);
            await page.getByRole('button', { name: 'Minimise timer', exact: true }).click();
            await screen.getByRole('button', { name: 'Finish session', exact: true }).click();
            await expect(page.locator('.today-review-root')).toBeVisible();
            await page.locator('.today-review-root').getByRole('button', { name: 'Back to session', exact: true }).click();
            await page.getByRole('button', { name: 'Back to Plan', exact: true }).click();
            expect(await page.evaluate(() => scrollY)).toBe(scroll);
            if (process.env.UNLXCK_SCREENSHOTS)
                await page.screenshot({ style: "nextjs-portal { display: none; }", animations: "disabled", path: `${process.env.UNLXCK_SCREENSHOTS}/plan-${width}.png`, fullPage: true });
            expect((await new AxeBuilder({ page }).include('.cm-root').analyze()).violations).toEqual([]);
            expect(errors).toEqual([]);
        });
