# UNLXCK Processor, DPA & International Transfer Verification

**Status:** Pre-launch internal verification record — processor checks complete.

## Rule
For each production processor, UNLXCK records its role, DPA/contract position, relevant processing location/sub-processors and UK international-transfer safeguards. Sensitive health and children's data must be minimised when sent to third parties.

## Verification register

| Provider | Purpose | Verification | Status |
|---|---|---|---|
| Supabase | Auth, database, storage | UNLXCK Pro project confirmed in Paris (`eu-west-3`). Supabase DPA, sub-processor controls and UK Addendum/SCC safeguards confirmed. Pro database backups are retained on the provider's documented backup schedule. No Supabase Edge Functions are currently deployed. | **VERIFIED** |
| OpenAI | AI-assisted plan/content processing | OpenAI DPA and UK Addendum/SCC safeguards confirmed. API data is not used for model training by default. Published sub-processors apply; eligible API usage may use additional retention controls such as Zero Data Retention where available. Minimise health context sent to the API. | **VERIFIED** |
| Vercel | Frontend hosting/deployment | UNLXCK production use confirmed on Vercel Pro. Current Vercel DPA covers Pro services and includes UK transfer safeguards and sub-processor controls. | **VERIFIED** |
| Hetzner | Backend infrastructure | UNLXCK server location confirmed as Nuremberg, Germany (`eu-central`). Hetzner Article 28 Data Processing Agreement / AVV confirmed accepted in the customer account. Hetzner publishes sub-processors; EU-hosted cloud workloads remain in the selected EU location, subject to documented operational/sub-processor access. | **VERIFIED** |
| Resend | Transactional email | Resend DPA, UK GDPR/SCC transfer framework and published sub-processors confirmed. Provider documentation states email data is retained for a limited default period. Keep health data out of transactional email unless necessary. | **VERIFIED** |
| Cloudflare Turnstile | Bot/abuse prevention | Cloudflare DPA, sub-processor framework and UK transfer safeguards confirmed. Turnstile processes device/network/security signals for abuse prevention; do not send athlete health data to Turnstile. | **VERIFIED** |

## Not used
**Sentry is not used by UNLXCK** and is therefore not a production processor for this register.

## Sensitive-data rule
UNLXCK processes health/injury information and data relating to children. Send third parties only the data necessary for their function. Production logs, monitoring, email and anti-abuse systems must not unnecessarily contain injury descriptions, symptoms, readiness responses or other health information.

## International transfers
Where processing involves a restricted UK transfer, retain evidence of the applicable adequacy position or safeguard, including an IDTA/UK Addendum where relevant, and complete any required transfer-risk assessment.

## Launch gate
All currently identified production processors in this register are **VERIFIED**. Re-open this launch gate if a new processor is added or an existing provider's contractual, hosting or transfer position materially changes.

## Review
Re-check this record when a provider, hosting region, data flow, DPA, sub-processor arrangement or transfer mechanism materially changes.
