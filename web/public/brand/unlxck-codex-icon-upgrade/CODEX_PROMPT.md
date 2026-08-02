# Upgrade UNLXCK to the new icon system

Work in the `vitalvightz/unlxck-gpt-webhook` repository.

The attached `assets/` folder is authoritative. Do not redraw, reinterpret, trace, recolour, stretch or add effects to the logo. Use the supplied files exactly, only renaming/copying them where the existing framework requires a conventional filename.

## Git workflow

1. Fetch the remote and pull the latest `Main` before editing.
2. Create a new branch named `codex/upgrade-unlxck-icons`.
3. Preserve unrelated local changes. Do not modify or merge PR #2182 as part of this task.
4. Make the implementation, run validation, commit it, push the branch and open a **draft PR** targeting `Main`.

## Required implementation

### 1. Audit the current icon system first

Inspect the actual repository and identify every current icon/logo reference, including at minimum:

- Next.js metadata in `web/app/layout.tsx` or any nested layout;
- the PWA manifest, whether it is a generated `manifest.ts`, JSON or webmanifest file;
- favicon and Apple touch icon files/routes;
- service-worker or PWA cache lists in `web/public/sw.js`;
- PWA asset tests such as `web/lib/pwa-assets.test.ts`;
- the logged-out landing page `/` and its shared brand/auth shell;
- any other reusable logo component used by logged-out pages.

Do not guess a selector or component. Confirm each replacement from the code and, for visible UI, from the rendered page.

### 2. Replace the installed-app and browser icons

Use these supplied files:

- standard PWA icon: `assets/app/app-192.png`;
- high-resolution PWA icon: `assets/app/app-512.png`;
- maskable PWA icons: `assets/maskable/app-maskable-192.png` and `assets/maskable/app-maskable-512.png`;
- Apple touch icon: `assets/app/apple-touch-icon.png`;
- browser favicon: prefer `assets/app/favicon.ico`, while preserving explicit 16×16 and 32×32 metadata where the current Next.js setup supports it;
- use `assets/app/favicon-16.png` and `assets/app/favicon-32.png` for those explicit sizes.

Update metadata and the manifest so:

- 192 and 512 standard icons have `purpose: "any"`;
- maskable variants have `purpose: "maskable"`;
- MIME types and sizes are correct;
- URLs match the actual copied public paths;
- no old icon URL remains as the active app icon;
- installed PWA, browser tab and iOS home-screen icon all use the new mark.

Use the current project conventions. Do not introduce a new icon library or runtime image-generation dependency.

### 3. Replace visible brand usage on the landing page

There must be at least one real in-page brand replacement in addition to the app/PWA icon update.

On `/`, replace the existing landing-page icon/logo mark with the new transparent white mark from `assets/brand/`. Use the closest supplied size to the actual rendered CSS dimensions:

- up to 24px rendered: `unlxck-mark-24.png`;
- 25–32px: `unlxck-mark-32.png`;
- 33–48px: `unlxck-mark-48.png`;
- 49–64px: `unlxck-mark-64.png`;
- 65–96px: `unlxck-mark-96.png`;
- 97–120px: `unlxck-mark-120.png`;
- larger: use the nearest larger supplied size, not a smaller file stretched up.

If the landing page uses a shared logged-out brand component, update that component so `/`, `/login`, `/signup`, `/forgot-password` and `/reset-password` remain visually consistent. Do not alter layout, copy, spacing, colours, diagonal/grid decoration work or signed-in workspace styling except where a small sizing adjustment is strictly required to fit the new mark.

The transparent mark is designed for dark brand surfaces. If the same component is used on a light surface, keep adequate contrast using the existing theme treatment rather than editing the asset.

### 4. Save and retain the useful size set

Copy the supplied assets into the repository under a clear, conventional structure inside `web/public/`. Retain:

- app sizes required by the live manifest and metadata;
- the two maskable sizes;
- favicon sizes and `.ico`;
- Apple touch icon;
- transparent brand sizes that are actually useful in the application.

Do not commit `assets/contact-sheet.png`, `assets/source/unlxck-logo-master.png` or unused duplicate sizes to the production public folder unless the repository already has an intentional brand-source directory. The source and contact sheet are for implementation/reference.

Avoid keeping two active versions of the old and new icon under confusing names. Remove obsolete public icon files only after proving no code, manifest, test or cache still references them.

### 5. Cache and update behaviour

If the service worker precaches icon URLs or uses a static cache version, update it so existing users receive the new files instead of a stale icon. Do not broadly clear unrelated caches or change offline behaviour.

### 6. Validation

Run the relevant existing commands from the correct package directory. At minimum:

- type checking;
- linting for changed frontend files;
- focused PWA/icon tests, including `web/lib/pwa-assets.test.ts` if present;
- production build if practical;
- inspect all icon files programmatically to confirm declared dimensions match actual dimensions;
- search the repository for old active icon paths after the change.

Render and check:

- `/` on desktop and 390px mobile;
- `/login`, `/signup`, `/forgot-password`, `/reset-password` if they share the changed brand component;
- dark and light mode where supported;
- browser favicon metadata;
- generated/served manifest entries;
- no broken image requests;
- no hydration mismatch;
- no change to the signed-in workspace logo unless it intentionally uses the same shared brand component and the result is visually correct.

Add or update focused tests so they fail when:

- required icon files are missing;
- manifest sizes/purposes are wrong;
- metadata points to non-existent files;
- the service-worker cache still references removed icon paths.

## Acceptance criteria

- New UNLXCK mark is used for the installed/PWA app icon.
- Browser favicon and Apple touch icon use the new mark.
- The landing page visibly uses the new mark, giving at least two distinct product changes overall.
- The correct standard and maskable assets are declared.
- Useful icon sizes are retained in the repository without unnecessary duplicate production assets.
- No old active icon path remains.
- Logged-out pages remain visually stable before and after hydration.
- Signed-in workspace styling and unrelated behaviour are unchanged.
- Tests, type check and build pass, or the draft PR clearly documents any pre-existing failure with evidence.

## Draft PR description

Include:

- exact icon files copied and their final public paths;
- every metadata/manifest/service-worker reference changed;
- which landing/shared component was updated;
- screenshots of `/` at desktop and 390px mobile;
- validation commands and outcomes;
- confirmation that old icon paths were searched for and removed or intentionally retained.
