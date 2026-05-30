\# Unlxck GPT Webhook — Codex Instructions



\## Project Identity



This repository powers Unlxck, a premium combat-sports and athlete performance platform.



Unlxck is not a generic fitness app. It should feel elite, direct, dark, athletic, and performance-led.



Default visual style:

\- Black/dark premium base

\- White bold typography

\- Red accents only for emphasis

\- Minimal luxury-combat aesthetic

\- No childish gradients

\- No generic SaaS feel

\- No soft wellness-app design

\- No unnecessary animations unless they improve clarity



\## Core Rule



Make small, controlled, reviewable changes.



Do not rewrite entire modules unless explicitly asked.



Do not remove existing logic unless there is a clear reason.



Do not simplify performance logic just to make code shorter.



\## Backend Priorities



Preserve the deterministic fight camp generation system.



Important areas:

\- Athlete intake parsing

\- Phase logic: GPP, SPP, TAPER

\- Strength module

\- Conditioning module

\- Rehab/injury module

\- Nutrition module

\- Recovery module

\- Mindset module

\- Supabase export logic



When editing backend logic:

1\. Inspect the current implementation first.

2\. Explain the planned change.

3\. Modify the smallest necessary area.

4\. Check for broken imports, missing fields, or changed output formats.

5\. Run available tests or sanity checks where possible.



\## Frontend Priorities



When editing UI:

\- Prioritise mobile-first layouts

\- Use strong hierarchy

\- Keep spacing clean

\- Make the app feel premium and athletic

\- Avoid generic cards unless styled with intent

\- Use clear CTAs

\- Use short, powerful copy



Unlxck UI should feel closer to:

\- elite sports-performance software

\- combat athlete dashboard

\- premium training intelligence platform



Not:

\- gym booking app

\- wellness blog

\- generic AI SaaS dashboard



\## Supabase Safety



Before changing anything related to Supabase:

\- Check existing schema usage

\- Do not guess table names

\- Do not change RLS assumptions blindly

\- Do not expose private user data

\- Do not alter environment variables without explaining why



\## Vercel / Deployment Safety



Before deployment-related changes:

\- Check build commands

\- Check environment variables

\- Check frontend/backend separation

\- Avoid changes that only work locally



\## Testing Discipline



Before finishing a task:

\- Run relevant tests if available

\- Run import checks for Python changes

\- Run build/lint checks for frontend changes if available

\- Show a short summary of changed files

\- Mention anything not verified



\## Communication Style



Be direct.



For every coding task, answer with:

1\. What changed

2\. Why it changed

3\. Files changed

4\. How to verify

5\. Any risks or follow-up work



Do not over-explain unless asked.

