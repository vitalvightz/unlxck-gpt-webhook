# UNLXCK Processor, DPA & International Transfer Verification

**Status:** Pre-launch internal verification record.

## Rule
For each production processor, UNLXCK records its role, DPA/contract position, relevant processing location/sub-processors and UK international-transfer safeguards. Sensitive health and children's data must be minimised when sent to third parties.

## Verification register

| Provider | Purpose | Verification | Status |
|---|---|---|---|
| Supabase | Auth, database, storage | UNLXCK Pro project confirmed in Paris (`eu-west-3`). Supabase DPA, sub-processor controls and UK Addendum/SCC safeguards confirmed. Pro database backups are retained on the provider's documented backup schedule. No Supabase Edge Functions are currently deployed. | **VERIFIED** |
| OpenAI | AI-assisted plan/content processing | OpenAI DPA and UK Addendum/SCC safeguards confirmed. API data is not used for model training by default. Published sub-processors apply; eligible API usage may use additional retention controls such as Zero Data Retention where available. Minimise health context sent to the API. | **VERIFIED** |
| Vercel | Frontend hosting/deployment | Current Vercel DPA verified for covered Pro/Enterprise services, with UK transfer safeguards and sub-processor controls. Connected Vercel account returned no UNLXCK project, so actual production use/plan is not confirmed. If UNLXCK does not use Vercel in production, remove it from this register. | **OPEN — confirm production use/plan** |
| Hetzner | Backend infrastructure | Hetzner provides Article 28 data-processing terms and publishes sub-processors. EU-hosted cloud workloads remain in the selected EU location, subject to documented operational/sub-processor access. | **OPEN — confirm UNLXCK server region and DPA accepted in account** |
| Sentry | Error monitoring | Sentry provides processor/data-protection terms and supports EU/Germany data residency. Production error reporting must minimise/redact athlete health information. | **OPEN — confirm UNLXCK project exists and its region** |
| Resend | Transactional email | Resend DPA, UK GDPR/SCC transfer framework and published sub-processors confirmed. Provider documentation states email data is retained for a limited default period. Keep health data out of transactional email unless necessary. | **VERIFIED** |
| Cloudflare Turnstile | Bot/abuse prevention | Cloudflare DPA, sub-processor framework and UK transfer safeguards confirmed. Turnstile processes device/network/security signals for abuse prevention; do not send athlete health data to Turnstile. | **VERIFIED** |

## Open launch checks
Only these account-specific checks remain:

1. **Vercel:** confirm whether UNLXCK is actually deployed on Vercel and, if so, the applicable plan. If not used, remove Vercel.
2. **Hetzner:** confirm the production server region and that the Hetzner DPA has been concluded/accepted in the customer account.
3. **Sentry:** confirm whether UNLXCK has a production Sentry project and, if so, its data region. If not used, remove Sentry.

## Sensitive-data rule
UNLXCK processes health/injury information and data relating to children. Send third parties only the data necessary for their function. Production logs, monitoring, email and anti-abuse systems must not unnecessarily contain injury descriptions, symptoms, readiness responses or other health information.

## International transfers
Where processing involves a restricted UK transfer, retain evidence of the applicable adequacy position or safeguard, including an IDTA/UK Addendum where relevant, and complete any required transfer-risk assessment.

## Launch gate
A provider that processes production personal data must be **VERIFIED** before public launch. Otherwise the integration must be removed/disabled or the outstanding contractual/transfer issue resolved.

## Review
Re-check this record when a provider, hosting region, data flow, DPA, sub-processor arrangement or transfer mechanism materially changes.
