import test from 'node:test';
import assert from 'node:assert/strict';
import './test-dom';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { StructuredPlanRenderer, CampDayCard } from './structured-plan-renderer';
import { buildCompletionIndex } from '@/lib/camp-map';
import type { StructuredPlan, StructuredDay } from '@/lib/types';
const day: StructuredDay = { date: '2026-10-25', sessions: [{ session_id: 'strength', title: 'Strength', session_type: 'strength', blocks: [{ block_id: 'squat', display_name: 'Squat', sets: 3, reps: 5, stop_rules: ['Stop for sharp knee pain.'], coaching_cues: ['Brace before each repetition.'] }] }] };
const plan: StructuredPlan = { plan_metadata: { plan_type: 'fight_camp' }, weeks: [{ week_index: 1, days: [day] }, { week_index: 2, days: [{ ...day, date: '2026-11-01' }] }], red_flag_rules: [{ severity: 'red', display_text: 'Chest pain stops training.' }] };
const click = async (el: Element | null) => { assert.ok(el); await act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })); }); };
test('Plan → session → exercise → Plan retains week, focus and safety', async () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    try {
        await act(async () => root.render(<StructuredPlanRenderer plan={plan} today={new Date('2026-10-25T12:00:00Z')}/>));
        assert.equal(container.querySelectorAll('.ex-row, iframe, video').length, 0);
        await click(container.querySelector('[data-week-pos="1"]'));
        const link = container.querySelector<HTMLButtonElement>('.cm-session-link')!;
        link.focus();
        await click(link);
        assert.equal(document.querySelectorAll('[role="dialog"]').length, 1);
        assert.match(document.querySelector('.cm-session-screen-body')?.textContent || '', /Chest pain stops training/);
        assert.equal(document.querySelectorAll('.ex-row').length, 1);
        assert.equal(document.querySelector('.sp-session-toggle'), null);
        assert.match(document.querySelector('.ex-row-stop')?.textContent || '', /sharp knee pain/);
        await click(document.querySelector('.ex-row-toggle'));
        const details = document.querySelectorAll('[role="dialog"]');
        assert.equal(details.length, 2);
        assert.match(details[1].textContent || '', /Brace before each repetition/);
        assert.match(details[1].textContent || '', /sharp knee pain/);
        await click(details[1].querySelector('[aria-label="Back to session"]'));
        await click(document.querySelector('[aria-label="Back to Plan"]'));
        assert.equal(document.querySelectorAll('[role="dialog"]').length, 0);
        assert.equal(container.querySelector('.cm-week-pill-selected')?.getAttribute('data-week-pos'), '1');
        assert.equal(document.activeElement, link);
    }
    finally {
        await act(async () => root.unmount());
        container.remove();
    }
});
for (const [status, date, label] of [['done', '2026-10-25', 'Completed'], ['modified', '2026-10-25', 'Completed'], ['started', '2026-10-25', 'In progress'], ['started', '2026-10-24', 'Missed'], ['', '2026-10-26', 'Upcoming']] as const) {
    test(`schedule ${status || 'unlogged'} ${date}`, async () => {
        const container = document.createElement('div');
        document.body.appendChild(container);
        const root = createRoot(container);
        const index = buildCompletionIndex(status ? [{ training_day: date, session_id: 'strength', status } as never] : []);
        try {
            await act(async () => root.render(<CampDayCard day={{ ...day, date }} completionIndex={index} currentTrainingDayIso="2026-10-25"/>));
            assert.equal(container.querySelector('.cm-session-status')?.textContent, label);
        }
        finally {
            await act(async () => root.unmount());
            container.remove();
        }
    });
}
test('empty and recovery weeks remain compact', async () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    try {
        await act(async () => root.render(<StructuredPlanRenderer plan={{ weeks: [{ week_index: 1, days: [] }] }}/>));
        assert.match(container.textContent || '', /No days scheduled/);
        await act(async () => root.render(<StructuredPlanRenderer plan={{ weeks: [{ week_index: 1, days: [{ date: '2026-10-25', day_type: 'rest', sessions: [] }] }] }}/>));
        assert.equal(container.querySelectorAll('.cm-session-link, .ex-row').length, 0);
    }
    finally {
        await act(async () => root.unmount());
        container.remove();
    }
});
test('calendar navigation preserves week selection and opens its selected training day', async () => {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    try {
        await act(async () => root.render(<StructuredPlanRenderer plan={plan} today={new Date('2026-10-25T12:00:00Z')}/>));
        const calendar = Array.from(container.querySelectorAll('button')).find(button => button.textContent === 'Calendar');
        await click(calendar!);
        assert.ok(container.querySelector('.cm-calendar'));
        await click(container.querySelector('.cm-calendar button:not(:disabled)'));
        await click(container.querySelector('.cm-session-link'));
        assert.ok(document.querySelector('.cm-session-screen'));
        await click(document.querySelector('[aria-label="Back to Plan"]'));
        assert.equal(calendar?.getAttribute('aria-pressed'), 'true');
    }
    finally {
        await act(async () => root.unmount());
        container.remove();
    }
});
for (const progressStatus of ['loading', 'unavailable'] as const)
    test(`live progress ${progressStatus} does not display stale completion counts`, async () => {
        const container = document.createElement('div');
        document.body.appendChild(container);
        const root = createRoot(container);
        try {
            await act(async () => root.render(<StructuredPlanRenderer plan={plan} today={new Date('2026-10-25T12:00:00Z')} progressStatus={progressStatus}/>));
            assert.match(container.querySelector('.cm-completion-label')?.textContent || '', progressStatus === 'loading' ? /Syncing progress/ : /Progress unavailable/);
            assert.equal(container.querySelectorAll('.cm-day-count').length, 0);
        }
        finally {
            await act(async () => root.unmount());
            container.remove();
        }
    });
