# UNLXCK UK Compliance Audit — Terms of Use & Privacy Notice

**Date of audit:** 17 August 2026
**Documents audited:** `docs/terms-of-use.md`, `docs/privacy-notice.md`, and their in-app renderings in `web/lib/legal-documents.ts`
**Supporting records reviewed:** children's policy, DPIA, data map/processor register, retention & user-rights policy, breach procedure, processor/transfer verification, regulatory intended-purpose
**Method:** documents read against the implementing code, not in isolation. Every finding below is tied to what the product actually does.

This is an internal compliance assessment, in the same register as the existing `docs/` compliance records. It is not legal advice and does not replace sign-off by a qualified solicitor, which is worth obtaining before the 19 August effective date given the special-category and children's data involved.

---

## Verdict

**Not ready for the 19 August 2026 effective date.** Four findings are launch blockers. The most serious is that the Privacy Notice, the processor register and the transfer-verification record all state a position on third-party processing that the code contradicts: **Sentry is fully deployed in both the frontend and the backend, including session replay, while three compliance documents record that it is not used.**

The underlying consent architecture is genuinely strong — better than most products at this stage. The problem is not the design of consent; it is that the published documents no longer describe the system, and that mandatory identity and contact information is still unwritten.

**Your own DPIA agrees:** `docs/health-data-lawful-basis-dpia.md` records residual risk as "**not yet acceptable for public launch**" pending six controls. Items 3 (retention periods), 4 (operational rights process) and 5 (processor/transfer verification) are not closed.

---

## Blockers — fix before the documents take effect

### B1. Sentry is undisclosed, unregistered, and running session replay over health data

**What the documents say**

| Source | Statement |
|---|---|
| `docs/data-map-processor-register.md:33` | "**Sentry is not used by UNLXCK** and is not a production processor." |
| `docs/processor-dpa-international-transfer-verification.md:20` | "**Sentry is not used by UNLXCK** and is therefore not a production processor for this register." |
| `web/lib/legal-documents.ts:14-16` | "Sentry is not listed as a processor, because UNLXCK does not use it" |
| `web/lib/legal-documents.test.ts:122` | A passing test asserts: `"Sentry is named nowhere — UNLXCK does not use it"` |

**What the code does**

- `web/package.json:16` — `@sentry/nextjs` 10.55.0 is a production dependency.
- `web/instrumentation-client.ts` — `Sentry.init()` with **`replaysSessionSampleRate: 0.1`** and **`replaysOnErrorSampleRate: 1.0`**. One in ten athlete sessions is recorded; every session that hits an error is recorded in full.
- `web/sentry.server.config.ts`, `web/sentry.edge.config.ts`, `web/instrumentation.ts`, `web/app/global-error.tsx`, `web/proxy.ts` — server, edge and client are all instrumented.
- `requirements.txt:13` — `sentry-sdk` 2.61.0 on the backend.
- `api/app.py:114` — `init_sentry()` is called unconditionally at application start.
- `api/services/today_readiness_boundary_core.py:113-119` — readiness-context failures are actively pushed to Sentry with `readiness_context_component` and `readiness_context_status` tags.
- `.env.example:25-30` and `web/.env.local.example:8-11` — `SENTRY_ORG=unlxck`, `SENTRY_PROJECT=javascript-nextjs`. A real Sentry organisation exists.

**Why this matters legally**

1. **Art. 30 UK GDPR** — the record of processing activities is inaccurate. A processor receiving data from a special-category service is missing entirely.
2. **Art. 13(1)(e)** — the Privacy Notice's "Service providers" section lists categories ("hosting, databases, AI processing, email and security services"). Error monitoring and **session recording** are not fairly described by any of those. A user reading the notice would not learn their session may be video-reconstructed.
3. **Ch. V UK GDPR** — Sentry Inc. is US-based. Unless the DSN points at Sentry's EU region, this is a restricted transfer with **no IDTA/UK Addendum and no transfer risk assessment on file**. Your own launch gate at `processor-dpa-international-transfer-verification.md:28` declares all processors VERIFIED — that gate was passed on a false premise and must be re-opened.
4. **Reg. 6 PECR** — Sentry Replay stores a session identifier in browser storage. Storing information on a user's terminal equipment requires consent unless *strictly necessary for a service the user explicitly requested*. The ICO does not treat analytics or session recording as strictly necessary. **There is no cookie/storage consent mechanism anywhere in the app.** PECR is enforceable by monetary penalty independently of UK GDPR.
5. **Art. 9 + Art. 35** — the DPIA assesses AI plan generation and processor flows. It does not assess session replay of an athlete entering injuries, pain and bodyweight. The replay config uses `maskAllText`, `maskAllInputs` and `blockAllMedia`, which is the right configuration and materially reduces the risk — but it does not eliminate it (URL paths, breadcrumbs, tags and `enableLogs: true` console capture sit outside the masking), and an unassessed risk is still an unassessed risk.
6. **Age Appropriate Design Code, standards 4, 10 and 11** — one in ten of those recorded sessions belongs to a 13–17-year-old, disclosed to a third-party processor that the child-readable notice does not mention. Standard 11 expects no disclosure of children's data without a compelling reason, documented.

**Remediation**

- Decide first: **keep Sentry or remove it.** If the honest answer is that error monitoring is worth it, keep it and document it properly. If session replay is not worth the children's-data exposure, disable replay (`replayIntegration`) and keep plain error monitoring — that is a much smaller compliance surface and I would recommend it as the default.
- Add Sentry to `data-map-processor-register.md` and `processor-dpa-international-transfer-verification.md`; execute/record the Sentry DPA and UK Addendum; confirm the data region.
- Name it in the Privacy Notice — both the markdown and `web/lib/legal-documents.ts` — describing error diagnostics and, if retained, session recording.
- Update the DPIA to cover replay, and record the AADC standard-11 justification for child sessions.
- If replay stays, implement a PECR-compliant consent mechanism and gate `Sentry.init` replay on it.
- **Invert `web/lib/legal-documents.test.ts:122`.** As written, that test enforces the error and will fail the build when someone fixes it. Replace it with an assertion that Sentry *is* named.
- Remove the stale claim in the `web/lib/legal-documents.ts:14-16` header comment.

---

### B2. Neither document identifies the trader, and both contact addresses are placeholders

`docs/terms-of-use.md:6` names the operator only as "**Unlxck**" — no legal entity, no company number, no registered office. `docs/terms-of-use.md:71` gives the contact as `[LEGAL/CONTACT EMAIL]`. `docs/privacy-notice.md:10` gives the privacy contact as `[ADD PRIVACY EMAIL BEFORE PUBLIC LAUNCH]`. No footer or page in `web/app/` carries company identity details.

This engages four separate obligations:

- **Art. 13(1)(a) UK GDPR** — the identity *and contact details of the controller* are mandatory content of a privacy notice. A notice published with a bracketed placeholder does not satisfy it.
- **Reg. 6, Electronic Commerce (EC Directive) Regulations 2002** — name, geographic address and email address must be available to recipients, easily, directly and permanently.
- **Consumer Contracts (Information, Cancellation and Additional Charges) Regulations 2013**, Sch. 2 — trader identity, geographic address and contact details must be given before the consumer is bound.
- **Companies Act 2006 s.82** and the Company, LLP and Business (Names and Trading Disclosures) Regulations 2015 — if Unlxck is incorporated, the registered name, company number, place of registration and registered office must appear on the website.

**Remediation:** resolve the legal entity, then populate the operator name, company number, registered office and both contact addresses across `docs/terms-of-use.md`, `docs/privacy-notice.md` and `web/lib/legal-documents.ts`. Add a site footer carrying the trading disclosures. This is unavoidable and cannot ship as a placeholder.

---

### B3. The data-rights route is conditional on an environment variable

`web/lib/legal-documents.ts:307-317` reads the privacy address from `NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL`. When it is unset, `web/app/settings/page.tsx:1193-1204` hides the deletion button and tells the athlete to use the beta-feedback form instead.

The engineering instinct here is right — offering a `mailto:` link to a placeholder address would be worse. But the consequence is that the *published* Privacy Notice directs users to `[ADD PRIVACY EMAIL BEFORE PUBLIC LAUNCH]` while the app quietly routes them somewhere else. Arts. 12(2) and 15–21 require a route that works, and Art. 12(3) starts a one-month clock from receipt. A DSAR arriving through the beta-feedback table has no owner, no logging against the statutory deadline and no identity-verification step.

`docs/data-retention-deletion-user-rights.md:56` already lists "publish a working route for privacy/data-rights requests" as a launch requirement. It is open.

**Remediation:** set the address, remove the conditional fallback path, and stand up the request log the breach procedure at `docs/data-breach-user-rights-procedure.md:11-17` already specifies. Also fill `[PRIVACY EMAIL]` and `[NAME / ROLE]` (privacy owner) in that procedure — an unnamed owner means no one is tracking the 72-hour breach clock.

---

### B4. The Privacy Notice's lawful bases do not cover the purposes it declares

`docs/privacy-notice.md:34-39` offers exactly two bases: Art. 6(1)(b) contract, and Art. 9(2)(a) explicit consent for health data.

But `docs/privacy-notice.md:24-30` declares these purposes: *"operate accounts, prevent abuse, troubleshoot problems and **improve UNLXCK**."*

Service improvement, abuse prevention, troubleshooting and security (Turnstile, at `data-map-processor-register.md:19`) are not *necessary for performance of the contract* with the athlete. The ICO's consistent position is that product improvement runs on **Art. 6(1)(f) legitimate interests**, which requires a documented Legitimate Interests Assessment and triggers the Art. 21 right to object. Declaring a purpose with no valid basis is an Art. 5(1)(a) and Art. 13(1)(c) failure.

Two knock-on effects:

- **The "Right to object" line is currently misleading.** `docs/privacy-notice.md:71` says "where the right applies, you may object". Under Art. 21 the right applies only to Art. 6(1)(e)/(f) processing. On the bases as drafted, it never applies — so the notice lists a right the user does not have. Once legitimate interests is properly declared, the right becomes real and must be described specifically.
- **Health data must not drift into improvement.** The consent wording in `web/lib/compliance.ts:66-67` covers use "to personalise my training". If injury or readiness data is used to improve the product or tune models, that is outside the Art. 9(2)(a) consent obtained. Either exclude health data from improvement purposes, or seek separate consent.

**Remediation:** add Art. 6(1)(f) to the lawful-bases section with named interests (security, abuse prevention, service improvement), write the LIA, rewrite the right-to-object line to state when it applies and how to exercise it, and state explicitly that health data is not used for product improvement.

---

## High

### H1. Relying on contract as the Art. 6 basis for 13–17-year-olds is fragile

Under English law a contract with a minor is generally voidable at the minor's option, outside the "necessaries" exception. Art. 6(1)(b) requires processing necessary for *performance of a contract to which the data subject is party*. Where that contract is voidable, the basis is shaky — and the ICO's children's guidance expressly asks controllers to consider whether the child can enter into the contract at all.

`docs/children-age-appropriate-use-policy.md:27` handles the *Art. 9* consent question well (13+ can consent to an ISS under DPA 2018 s.9, subject to capacity). It does not address the *Art. 6* contract question.

**Remediation:** record the assessment, and consider relying on legitimate interests rather than contract for under-18 core processing, with an LIA weighted to the child's best interests.

### H2. Art. 22 is asserted away rather than assessed

`docs/privacy-notice.md:44` states UNLXCK "does not currently **intend** these decisions to produce legal or similarly significant effects about you."

Intent is not the test. Art. 22 applies where a decision is based solely on automated processing and produces legal or similarly significant effects. The system automatically restricts or withholds training on the basis of health data (`api/compliance_guards.py`, `fightcamp/plan_pipeline_runtime.py:323`). My assessment is that training restriction most likely falls short of "similarly significant" — but the notice should record a reasoned conclusion, not a statement of intent, and Recital 71 and the ICO both counsel additional caution where the subject is a child.

**Remediation:** restate as a conclusion with reasoning, and describe the route to human review. Art. 13(2)(f) also requires meaningful information about the logic involved where Art. 22 does apply — worth pre-empting.

### H3. Retention has criteria, not periods

`docs/privacy-notice.md:52-59` and `docs/data-retention-deletion-user-rights.md:8-18` say data is kept "while needed" and "reviewed for deletion on account closure". Art. 5(1)(e) and Art. 13(2)(a) expect a period, or at minimum the criteria used to determine it. "Review on account closure" is a trigger, not a period, and leaves data in place indefinitely if no review happens.

Your own policy concedes this at `data-retention-deletion-user-rights.md:20`: "Exact operational periods not already enforced in code must be documented and implemented before public launch."

Screenshots are the one category done properly — `api/services/feedback_service.py:124-126` enforces the 90-day rule the notice promises. Note one gap: the value comes from `FEEDBACK_SCREENSHOT_RETENTION_DAYS` with a 90 default and **no upper clamp**, so a misconfigured environment could silently exceed the published commitment. Clamp it to 90.

### H4. No portability route exists

Art. 20 covers data provided by the athlete and processed on consent or contract — which is most of the profile, intake and training history. There is no export in Settings and no documented manual procedure. Manual fulfilment is legally acceptable; the absence of any procedure is not. `data-retention-deletion-user-rights.md:56-59` lists this as an open launch requirement.

**Remediation:** a documented runbook is sufficient for launch. Self-serve export can follow.

---

## Medium

### M1. Transfer disclosure is missing the "how to get a copy" limb
`docs/privacy-notice.md:49-50` describes the safeguards used but not how a user obtains a copy of them. Art. 13(1)(f) requires reference to the means to obtain a copy. One sentence fixes it.

### M2. No processors are named
The notice describes categories only. Categories satisfy Art. 13(1)(e) as a strict matter of law, so this is not a breach. But for a service processing children's health data, AADC standard 4 (transparency) points toward naming them, and you already maintain the list in `data-map-processor-register.md`. Naming Supabase, OpenAI, Vercel, Hetzner, Resend, Cloudflare and Sentry costs nothing and closes the gap between the internal register and the public notice.

### M3. Privacy Notice versioning is coupled to consent versioning
`web/lib/legal-documents.ts:177` sets `PRIVACY_NOTICE.version = HEALTH_CONSENT_VERSION`. These are different things. Editing the notice for an unrelated reason either forces every athlete to re-consent to health processing, or creates pressure not to bump the version at all — leaving the notice effectively unversioned. Since the Sentry fix requires a notice update, this bites immediately.

**Remediation:** introduce a distinct `PRIVACY_NOTICE_VERSION` alongside `HEALTH_CONSENT_VERSION` in both `web/lib/compliance.ts` and `api/compliance.py`.

### M4. Liability clause has no cap
`docs/terms-of-use.md:51-56` correctly preserves what cannot lawfully be excluded and preserves statutory rights — but sets no cap on liability at all. That is a gap against the company, not the user. Any cap must survive the Consumer Rights Act 2015 s.62 fairness test, and s.65 prohibits excluding liability for death or personal injury from negligence — which matters more than usual for a training-safety product. Worth adding an explicit statement that such liability is not excluded, alongside a fair cap on other losses.

### M5. Paid-services terms are deferred, and the regime is tightening
`docs/terms-of-use.md:58-59` defers payment terms. Before charging, you will need: the 14-day cancellation right and model cancellation form under the Consumer Contracts Regulations 2013; for digital content supplied immediately, express consent plus acknowledgement that the cancellation right is lost; and CRA 2015 Part 1 Ch. 3 digital-content quality rights. Also verify the commencement position of the **DMCC Act 2024** subscription-contracts regime (reminder notices, cooling-off, easy exit) — check whether it is in force before launching subscriptions rather than assuming either way.

### M6. Age assurance is self-declaration only
Enforcement is solid — `api/compliance.py`, a profile trigger and an `auth.users` trigger all reject under-13 (`supabase/migrations/20260817120000_add_compliance_age_and_consent.sql`). But nothing stops a 15-year-old typing an adult date of birth to reach the adult weight-cut surface. AADC standard 3 requires assurance *proportionate to the risks*, and aggressive weight-cut content for a minor is a high-risk outcome. Self-declaration is defensible at private-trial scale; record that reasoning in the DPIA and set a review trigger at public scale.

---

## Low / watch list

- **L1.** `web/lib/legal-documents.ts:10-18` cites PR #2312 and claims the canonical Terms still hold `[LEGAL OPERATOR NAME]` and `[DATE]`. Both are now populated in `docs/terms-of-use.md`. The comment is stale and justifies a drift that no longer exists.
- **L2.** Terms carry "Version: 0.1 pre-launch" with an effective date of 19 August 2026. A version marker saying "pre-launch" on a live contract is incoherent — bump to 1.0 at launch.
- **L3.** Cloudflare Turnstile at auth is defensible as strictly necessary under PECR reg. 6(4) (security for a service the user requested), so it does not need consent. Record that reasoning so the position is documented rather than assumed.
- **L4.** Push notifications are currently service/safety only, which is correct. Any marketing push will engage PECR reg. 22 and require opt-in consent — and for under-18s, the AADC's nudge rules in `children-age-appropriate-use-policy.md:35`.
- **L5.** Online Safety Act 2023 is out of scope while there are no user-to-user features. The children's policy review trigger at line 56 already covers social/community features; make the OSA duty explicit in that trigger.
- **L6.** Consider documenting the "no DPO required" assessment. Art. 37(1)(c) turns on *large scale* special-category processing as a core activity. At launch scale the conclusion is almost certainly that no DPO is needed, but for a health app that is a decision worth recording rather than leaving unaddressed.

---

## What is done well

Worth stating plainly, because it is unusual to see this done properly:

- **Consent architecture is correct.** Health-data consent is separate from Terms, versioned, server-stamped, and withdrawable in one click from Settings — satisfying Art. 7(3)'s "as easy to withdraw as to give".
- **Consent is not bundled with the account.** `web/lib/compliance.ts:222-224` deliberately excludes health consent from the signup gate, with the reasoning recorded inline: bundling would make it not freely given under Art. 7(4) and invalidate the Art. 9(2)(a) basis. Correct, and correctly explained.
- **Consent evidence cannot be self-written.** The `private.prevent_client_compliance_writes` trigger blocks any non-service-role write to consent columns, so an athlete cannot backdate their own consent and an admin cannot stamp it from a browser. Evidence that the subject can forge is not evidence.
- **Age assurance fails safe.** `api/compliance.py:110-120` treats an unknown date of birth as a minor, so a gap in age data withholds the adult weight-cut surface rather than granting it.
- **The 13+ floor is enforced in three independent places** — API, profile trigger, and an `auth.users` trigger that holds even if someone calls Supabase's signup endpoint directly.
- **Age-appropriate copy is real**, not a checkbox: three registers keyed to server-derived bands, with an explicit rule in the comments that shortening must never mean disclosing less.
- **The regulatory boundary is well drawn.** `docs/regulatory-intended-purpose.md` keeps UNLXCK clear of the medical-device perimeter, and the Terms and Privacy Notice both carry consistent "not medical care" language.
- **Sentry's PII posture is conservative** where it exists: `send_default_pii=false`, an aggressive `before_send` scrubber covering injuries, pain, notes and intake, and full masking on replay. The failure is one of disclosure and governance, not of engineering care.

---

## Remediation checklist

**Before 19 August (blockers)**

1. Decide Sentry's future; if kept, register it, execute the DPA, confirm the region, add UK transfer safeguards, update the DPIA, and disclose it in both documents.
2. Invert the `legal-documents.test.ts:122` assertion so the fix is not blocked by a test.
3. If session replay is retained, build PECR-compliant storage consent and gate replay on it.
4. Resolve the legal entity; populate operator name, company number, registered office and both contact addresses; add website trading disclosures.
5. Set `NEXT_PUBLIC_PRIVACY_CONTACT_EMAIL`, remove the fallback path, stand up the DSAR log, and name the privacy owner.
6. Add Art. 6(1)(f) with an LIA; rewrite the right-to-object line; state that health data is not used for improvement.

**Shortly after**

7. Record the Art. 6 basis assessment for under-18 contracts.
8. Restate the Art. 22 position as a reasoned conclusion with a human-review route.
9. Set concrete retention periods; clamp screenshot retention at 90 days.
10. Write the portability runbook.
11. Split `PRIVACY_NOTICE_VERSION` from `HEALTH_CONSENT_VERSION`.
12. Add the transfer "copy of safeguards" sentence; name processors.
13. Re-run the DPIA decision at `health-data-lawful-basis-dpia.md:41` and record whether residual risk is now acceptable.

**Before charging money**

14. Consumer Contracts Regulations pre-contract information, 14-day cancellation and model form; digital-content consent wording; check DMCC 2024 subscription commencement; add a liability cap tested for CRA fairness.

---

## Remediation log

The findings above are kept as-found. This section records what has since been actioned.

### 17 August 2026 — first remediation pass

| Finding | Status | What changed |
|---|---|---|
| **M3** Notice/consent version coupling | **Closed** | `PRIVACY_NOTICE_VERSION` added to `api/compliance.py` and `web/lib/compliance.ts`, notice moved onto it. Verified the notice can now be revised without re-collecting Art. 9(2)(a) consent or taking health features offline. Done first, because every other notice fix depended on it. |
| **B4** Lawful bases | **Closed** | Art. 6(1)(f) added with named interests; `docs/legitimate-interests-assessment.md` written; right-to-object rewritten to state when it applies; explicit statement added that health data is not used for product improvement. |
| **H2** Art. 22 asserted not assessed | **Closed** | Restated as a reasoned conclusion with the child-caution caveat, plus a human-review route. |
| **M1** Transfer safeguards copy | **Closed** | "You can ask us for a copy of the safeguard we rely on" added to both copies. |
| **H3** Screenshot retention ceiling | **Closed** | `screenshot_retention_days()` now clamps at 90. Verified no environment value can exceed the published commitment. *(The wider retention-period work remains open.)* |
| **L1** Stale drift comment | **Closed** | PR #2312 comment removed; the test-file header claiming the canonical docs live on another branch corrected — they are in this repo and the comparison test is live. |
| **L3** Turnstile PECR position | **Closed** | `docs/cookies-and-local-storage.md` written, registering every cookie and storage key with its reg. 6 assessment. Sentry Replay is recorded there as a known unremediated gap rather than a compliant position. |
| **L6** DPO assessment | **Closed** | Recorded in the DPIA as a reasoned "not required at current scale", with reassessment triggers. |
| **H1** Under-18 Art. 6 basis | **Logged** | Recorded as an open question in the DPIA. The assessment itself is still to be done. |

**Deliberately not done in this pass:**

- **M2 (name processors)** — a passing test at `legal-documents.test.ts:94` *requires* the notice to describe categories without naming providers. Reversing that is a deliberate decision, not a drafting fix, and it is entangled with the Sentry question: naming six live processors while omitting the seventh would introduce a fresh accuracy defect rather than close one.
- **L2 (Terms version → 1.0)** — `TERMS_VERSION` gates acceptance, so bumping it re-collects agreement from every athlete. It should ride with the B2 entity fix so athletes are asked once, not twice.
- **B2, B3, and retention periods** — blocked on the legal entity, the privacy address, and the retention decisions respectively.

### Verification

`web` unit suite 1238/1238 pass, including the canonical-vs-in-app comparison; `tsc --noEmit` clean. The two Python changes were verified directly (version split does not disturb consent gating; the retention clamp holds across valid, oversized, zero and malformed inputs).

## Review triggers

Re-run this audit when: a processor is added or removed; session replay, analytics or marketing tooling is introduced; payments launch; coach/parent/gym visibility of junior athlete data is enabled; community or user-to-user features are added (Online Safety Act); under-13 access is contemplated; or the Art. 9 consent wording changes.
