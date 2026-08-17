# UNLXCK Legitimate Interests Assessment

**Basis assessed:** Article 6(1)(f) UK GDPR
**Status:** Adopted. Supports the "Lawful bases" section of `docs/privacy-notice.md`.

## Why this exists

The Privacy Notice previously offered only Article 6(1)(b) (contract) and Article 9(2)(a) (explicit consent for health data), while declaring purposes those bases do not reach: security, abuse prevention, fault investigation and service improvement. None of those is *necessary for performance of the contract* with the athlete, so each needs its own basis. This assessment records the Article 6(1)(f) analysis for them.

## Absolute exclusion: health data

**No special-category data is processed under Article 6(1)(f) at UNLXCK, for any purpose in this assessment, in any form.** This is a hard boundary, not a default that a future purpose can argue its way past.

Specifically, health data — injuries, pain, soreness, fatigue, sleep, readiness, symptoms, recovery, bodyweight, target weight, and anything from which health status can be inferred — **must not** be used to:

- measure, analyse or report on product performance or engagement;
- prioritise, design, evaluate or A/B test features;
- train, fine-tune, evaluate or benchmark any model, including via a third party;
- build aggregate datasets, dashboards or research outputs, even where identifiers are stripped;
- populate examples, fixtures, demos or test data; or
- inform any decision other than the individual athlete's own training and safety.

Health data runs on **Article 9(2)(a) explicit consent** and is used only to build and adapt that athlete's own training and to apply safety rules to it. That is the whole of the consent the athlete gave, and it is the whole of what the data may be used for.

**Why the boundary is absolute rather than balanced.** Article 9(1) prohibits processing special-category data unless an Article 9 condition applies. Legitimate interests is an Article 6 basis and satisfies nothing under Article 9 — so there is no version of the balancing test that could authorise health data for product improvement. It is not a close call to be weighed; it is outside the basis entirely. Consent obtained "to personalise my training" does not stretch to cover it either: using it for improvement would be processing beyond the specified purpose, contrary to Article 5(1)(b).

**Aggregation and anonymisation do not create an exception.** If a dataset can be re-linked to an athlete it is still personal data. Genuinely anonymous, irreversibly aggregated statistics fall outside UK GDPR — but the anonymisation itself is processing of the underlying health data, and needs its own basis. Do not treat "we only looked at aggregates" as a defence.

**If a future purpose appears to need health data, the answer is separate explicit consent for that purpose, or no processing.** Do not revisit this assessment looking for room; there is none.

## Scope

| Purpose | Data used | Not used |
|---|---|---|
| Platform security and availability | Account identifiers, IP, device/technical metadata, security events | Injury, readiness, pain, nutrition or bodyweight data |
| Abuse prevention at signup and login | Device/network signals via Cloudflare Turnstile, rate-limit counters | Any health information |
| Fault investigation and diagnostics | Error events, technical context, scrubbed request metadata | Injury descriptions, symptoms, readiness answers — actively scrubbed (`api/sentry_config.py`) |
| Service improvement | Aggregate feature usage, generation reliability and failure rates | Health information in any form; individual athlete plans as training material; anything from which health status can be inferred |

## The three-part test

### 1. Purpose test — is there a legitimate interest?

Yes, and they are conventional operator interests rather than novel ones:

- **Security and abuse prevention.** UNLXCK holds special-category data about children. Keeping unauthorised people out of it is not merely a business interest — it is a direct protection for the athletes themselves, and Recital 49 expressly recognises network and information security as a legitimate interest.
- **Fault investigation.** The product makes safety decisions (restricting or withholding training). A fault that silently degrades those decisions is an athlete-safety problem, not only an availability problem.
- **Service improvement.** Understanding which features work lets UNLXCK build a better product. This is the weakest of the four interests and is treated accordingly below.

Third parties and the wider public also benefit from the first two: athletes other than the individual whose data is processed are protected by the same controls.

### 2. Necessity test — is the processing necessary?

- **Security / abuse prevention.** Yes. There is no way to keep credential-stuffing and automated signup abuse off an authentication endpoint without processing device and network signals. A less intrusive alternative that works does not exist.
- **Fault investigation.** Yes, but only in scrubbed form. The necessity is for *technical* context — what broke, where, in what state — not for the athlete's health inputs. The scrubber in `api/sentry_config.py` enforces that boundary, and the necessity claim depends on it continuing to.
- **Service improvement.** Necessary only in aggregate, and only over non-health signals. Improving the product does not require reading an athlete's health record — which is fortunate, because Article 9 would not permit it under this basis regardless of necessity. What is necessary here is knowing which features are used and where generation fails, neither of which needs health data.

### 3. Balancing test — do the individual's interests override?

**Reasonable expectations.** An athlete signing up to a training app reasonably expects the operator to keep the account secure, to fix faults, and to work out which features are worth building. None of this is a surprising use.

**Impact on the individual.** Low for all four purposes. No decision about the athlete is made on this basis — training adaptation runs on their own health data under consent, not on anything assessed here. There is no profiling for advertising, no sale of data, no disclosure to anyone outside the processors in the register.

**Children.** This is the factor carrying the most weight, since users may be as young as 13, and Recital 38 requires specific protection for children.

- The two strongest interests — security and abuse prevention — protect children *more* than adults, because the data at risk is children's health data. The balance favours processing.
- Fault investigation is neutral provided the health scrubbing holds.
- **Service improvement is the one to constrain.** It carries the weakest interest and the least benefit to the child. It is therefore limited to aggregate technical and usage signals, never health information, and never a child's individual record examined as product research.

**Safeguards relied on in this balance:**
- health data is excluded from every purpose in this assessment;
- `api/sentry_config.py` scrubs injuries, pain, notes, intake, goals and credentials before any diagnostic event leaves the service;
- the processor register bars sending health data to Turnstile, Resend and other non-health processors;
- the right to object is offered in the Privacy Notice and is honoured on request;
- no advertising, no data sale, no third-party profiling.

**Outcome:** the legitimate interests are not overridden, for all four purposes, subject to the constraints above.

## Right to object

Article 21 applies to processing under this basis. The Privacy Notice now says so explicitly and describes how to exercise it, replacing the previous "where the right applies" wording, which was uninformative and — while the notice claimed contract as the only basis — described a right the athlete did not actually have.

On objection UNLXCK stops the processing unless it can demonstrate compelling legitimate grounds that override the athlete's interests. For security and abuse prevention such grounds will usually exist, since the alternative is an unprotected authentication surface over children's health data; the reasoning must still be recorded per objection rather than assumed. For service improvement there is no such argument, and an objection is simply honoured.

## Review

Reassess when: a new purpose is proposed under this basis; any health or health-inference data is proposed for a purpose in scope here (which would require consent instead, not a rebalanced LIA); analytics, advertising or session-recording tooling is introduced; a processor is added; or the user base changes materially in age profile or scale.

This is an internal compliance assessment, not legal advice.
