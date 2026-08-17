# UNLXCK Legitimate Interests Assessment

**Basis assessed:** Article 6(1)(f) UK GDPR
**Status:** Adopted. Supports the "Lawful bases" section of `docs/privacy-notice.md`.

## Why this exists

The Privacy Notice previously offered only Article 6(1)(b) (contract) and Article 9(2)(a) (explicit consent for health data), while declaring purposes those bases do not reach: security, abuse prevention, fault investigation and service improvement. None of those is *necessary for performance of the contract* with the athlete, so each needs its own basis. This assessment records the Article 6(1)(f) analysis for them.

**Health data is out of scope of this assessment.** Special-category data is never processed under legitimate interests at UNLXCK — it runs on Article 9(2)(a) explicit consent and is used only to build, adapt and apply safety rules to the athlete's own training.

## Scope

| Purpose | Data used | Not used |
|---|---|---|
| Platform security and availability | Account identifiers, IP, device/technical metadata, security events | Injury, readiness, pain, nutrition or bodyweight data |
| Abuse prevention at signup and login | Device/network signals via Cloudflare Turnstile, rate-limit counters | Any health information |
| Fault investigation and diagnostics | Error events, technical context, scrubbed request metadata | Injury descriptions, symptoms, readiness answers — actively scrubbed (`api/sentry_config.py`) |
| Service improvement | Aggregate feature usage, generation reliability and failure rates | Health information; individual athlete plans as training material |

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
- **Service improvement.** Necessary only in aggregate. Improving the product does not require reading an identified athlete's plan or health record, so it must not, and does not, do so.

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
