/** Content-fidelity snapshots now visit the dedicated session screen rather than
 * depending on prescriptions being pre-rendered inside the Plan accordion. */
import '../components/test-dom';
import { act, type ReactElement } from 'react';
import { createRoot } from 'react-dom/client';
export async function renderPlanSessionViews(element: ReactElement): Promise<string> {
    const container = document.createElement('div');
    document.body.appendChild(container);
    const root = createRoot(container);
    const views: string[] = [];
    try {
        await act(async () => root.render(element));
        const links = Array.from(container.querySelectorAll<HTMLButtonElement>('.cm-session-link'));
        for (const link of links) {
            await act(async () => link.click());
            const view = document.querySelector('.cm-session-screen');
            if (!view)
                throw new Error('Session screen did not open');
            views.push(view.innerHTML);
            const back = document.querySelector<HTMLButtonElement>('[aria-label="Back to Plan"]');
            if (!back)
                throw new Error('Session back navigation missing');
            await act(async () => back.click());
        }
        return views.join('\n');
    }
    finally {
        await act(async () => root.unmount());
        container.remove();
    }
}
