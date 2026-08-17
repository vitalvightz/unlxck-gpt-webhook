# UNLXCK Processor, DPA & International Transfer Verification

**Status:** Pre-launch internal verification record.

## Rule
UNLXCK must identify every third party that processes personal data on its behalf, confirm an appropriate UK GDPR Article 28 contract/DPA is in place where required, identify relevant sub-processors and hosting locations, and determine whether any restricted international transfer occurs.

Where a restricted transfer occurs, UNLXCK must document the lawful transfer mechanism and any required transfer risk assessment before public launch.

## Processor register verification

| Provider | Main purpose | Data potentially involved | DPA / Article 28 terms | Hosting / transfer position | Status |
|---|---|---|---|---|---|
| Supabase | Authentication, database and storage | Account, profile, training, health/injury and usage data | [VERIFY] | [VERIFY REGION + SUB-PROCESSORS] | OPEN |
| OpenAI | AI-assisted plan/content processing | Prompt/context data, potentially including athlete health/training information | [VERIFY] | [VERIFY UK TRANSFER POSITION + SUB-PROCESSORS] | OPEN |
| Vercel | Frontend hosting/deployment | Technical/request data and any server-side data processed through deployed services | [VERIFY] | [VERIFY] | OPEN |
| Hetzner | Backend infrastructure | Application/API data processed by backend | [VERIFY] | [VERIFY SERVER REGION] | OPEN |
| Sentry | Error monitoring | Technical/error data; ensure sensitive athlete data is minimised/redacted | [VERIFY] | [VERIFY] | OPEN |
| Resend | Transactional email | Email address and message metadata/content | [VERIFY] | [VERIFY] | OPEN |
| Cloudflare Turnstile | Abuse/bot prevention | Device/network/request information | [VERIFY ROLE/TERMS] | [VERIFY] | OPEN |

## Verification checklist
For each provider, record evidence of:

1. controller/processor role;
2. binding DPA or equivalent Article 28 terms where the provider acts as processor;
3. processing purpose and data categories;
4. confidentiality and security commitments;
5. sub-processor terms/list and change-notification mechanism;
6. assistance with data-subject rights, breaches and DPIAs;
7. deletion/return provisions when service ends;
8. audit/compliance information;
9. countries/regions in which data may be processed; and
10. international-transfer mechanism where required.

## International transfers
A provider being headquartered outside the UK does not by itself determine the transfer position. Check where UNLXCK data is actually transferred or made accessible and whether the recipient is covered by UK adequacy regulations or another permitted safeguard.

Where an appropriate safeguard is required, verify the applicable mechanism, such as the UK International Data Transfer Agreement (IDTA) or UK Addendum to the EU Standard Contractual Clauses, and complete any required transfer risk assessment.

Do not mark a provider **VERIFIED** solely because it publishes a privacy policy.

## Sensitive-data rule
Because UNLXCK processes health/injury information and data relating to children, processor due diligence must consider the sensitivity and risk of the processing. Minimise health data sent to third parties, particularly monitoring/analytics services, and ensure production logs and error reports do not unnecessarily expose athlete health information.

## Launch gate
Public launch is blocked until all providers that process UNLXCK personal data are either:

- **VERIFIED** — role, contract/DPA, sub-processors and transfer position documented; or
- **REMOVED / DISABLED** — the integration does not process production personal data.

Any unresolved restricted international transfer is a launch blocker.

## Review
Re-check this record when adding a provider, changing hosting region, enabling a new data flow, materially changing a provider's use, or receiving notice of relevant sub-processor/transfer changes.
