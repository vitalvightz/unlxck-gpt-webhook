# Health Data Lawful Basis & DPIA

## Scope
UNLXCK processes athlete health-related data including injuries, soreness, fatigue, sleep, readiness, bodyweight and related safety/adaptation decisions.

## Lawful Basis
- **Article 6:** provisionally Article 6(1)(b) — processing necessary to provide the requested UNLXCK service.
- **Article 9:** provisionally Article 9(2)(a) — explicit consent for health-data processing.
- Do not rely on medical-treatment grounds unless UNLXCK’s regulatory status and operating model change.

Explicit consent must be specific, affirmative, recorded, separate from general Terms, and withdrawable.

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
