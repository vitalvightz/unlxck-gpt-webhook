# Health Data Lawful Basis & DPIA

## Scope
UNLXCK processes athlete health-related data including injuries, soreness, fatigue, sleep, readiness, bodyweight and related safety/adaptation decisions.

## Lawful Basis
- **Article 6:** provisionally Article 6(1)(b) — processing necessary to provide the requested UNLXCK service.
- **Article 6 (non-contract purposes):** Article 6(1)(f) legitimate interests for security, abuse prevention, fault investigation and service improvement. Assessed in `docs/legitimate-interests-assessment.md`. Health data is excluded from every purpose on this basis.
- **Article 9:** provisionally Article 9(2)(a) — explicit consent for health-data processing.
- Do not rely on medical-treatment grounds unless UNLXCK’s regulatory status and operating model change.

Explicit consent must be specific, affirmative, recorded, separate from general Terms, and withdrawable.

**Open question — Article 6 for under-18s.** A contract with a minor is generally voidable at the minor’s option under English law, which weakens Article 6(1)(b) as the basis for athletes aged 13–17. Assess whether legitimate interests, weighted to the child’s best interests, is the sounder basis for under-18 core processing, and record the outcome here.

## Data Protection Officer

A DPO is mandatory under Article 37(1)(c) where the core activities involve **large scale** processing of special-category data. UNLXCK processes special-category health data as a core activity, so only the scale limb is in question.

**Assessment:** at private-trial and initial-launch scale — a single-operator product with a small athlete base, no advertising, no data sale and no cross-controller sharing — the processing is not large scale within the meaning of Recital 91, which distinguishes it from processing by an individual practitioner and points at volume, breadth, duration and geographic reach. **No DPO is required.**

This is a decision, not an omission, and it does not remove the underlying obligations: someone must still own data-protection responsibility. That owner is named in `docs/data-breach-user-rights-procedure.md` and is accountable for rights-request deadlines, breach assessment and this DPIA.

**Reassess** if the athlete base grows substantially, if coach/parent/gym sharing is enabled, if processing extends beyond the UK user base, or if profiling for any purpose other than the athlete’s own training is introduced.

## DPIA
**Processing:** UNLXCK uses health-related athlete inputs to generate, adapt, restrict or withhold training guidance and may send relevant context to service providers used to operate the product.

**Main risks:**
- incorrect injury/readiness interpretation causing unsafe reliance;
- excessive collection or retention of sensitive data;
- unauthorised athlete-data access;
- users misunderstanding automated guidance as diagnosis or treatment;
- third-party processing or international transfers without adequate safeguards;
- inability to exercise privacy rights or withdraw consent effectively.

**Existing controls:**
- regulatory boundary prohibits diagnosis/treatment claims;
- server-authoritative safety logic and medical escalation language;
- own-row RLS and backend-controlled cross-athlete admin access;
- private storage and authentication;
- structured decision history rather than silent plan changes;
- screenshot retention/deletion controls.

## Required Before Public Launch
1. Add explicit health-data consent and record its version/time.
2. Publish a Privacy Notice explaining health data, purposes, processors, AI use, retention and rights.
3. Set retention periods for all health-related records.
4. Provide an operational access/deletion/withdrawal process.
5. Verify processor agreements and international-transfer safeguards.
6. Reassess this DPIA when injury, nutrition, AI, coach-sharing or medical-facing features materially change.

## Decision
Residual risk is **not yet acceptable for public launch** until the required controls above are implemented and documented.

This is an internal compliance assessment, not legal advice.
