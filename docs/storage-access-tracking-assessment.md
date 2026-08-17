# UNLXCK Storage, Cookies & Tracking Assessment

## Purpose
Internal assessment of cookies, local storage, SDKs and similar storage/access technologies used by UNLXCK. The goal is to use consent only where UK PECR requires it.

## Rule
UNLXCK must tell users about storage/access technologies it uses. Prior consent is required unless a PECR exception applies.

Current ICO guidance recognises exceptions including:
- strictly necessary storage/access needed to provide a service requested by the user;
- statistical/analytics use that meets the statutory conditions; and
- appearance/functionality preferences that meet the statutory conditions.

Where the statistical or appearance exception is relied upon, provide a simple free means to object where required.

## Current UNLXCK assessment

| Technology / use | Likely purpose | Current position |
|---|---|---|
| Supabase authentication/session storage | Sign-in and account security | Likely strictly necessary if limited to this purpose |
| UNLXCK appearance preference/local storage | Remember dark/light or similar user preference | May fall within the appearance exception; disclose and provide objection control where required |
| Private-trial / app state storage required to operate requested features | Service operation | Assess individually; strictly necessary use may not require consent |
| Cloudflare Turnstile | Authentication abuse/bot prevention | Security/service necessity; verify deployed browser storage/access behaviour before launch |
| Vercel platform logs/hosting | Server-side request/technical logs | PECR consent generally concerns storage/access on the user's device; separately disclose personal-data processing where applicable |
| Vercel Analytics or equivalent analytics | Product usage measurement | No `@vercel/analytics` integration was identified in the repository check on 17 August 2026; reassess if analytics is enabled through configuration or later added |
| Advertising pixels / behavioural tracking | Advertising/profiling | No such tool should be added without prior compliance review; normally expect consent |
| Push subscription/browser notification data | Deliver notifications requested by the user | Permission flow is handled by browser/platform; assess any additional device storage separately |

## Not used
**Sentry is not used by UNLXCK** and is therefore excluded from the production tracking assessment.

## Launch decision
A generic cookie banner is **not automatically required**. Before launch, audit the deployed app in-browser and list every cookie, local-storage/session-storage key, SDK, script, tag and other device storage/access operation.

For each item record:
1. provider;
2. information stored/accessed;
3. purpose;
4. lifetime;
5. first or third party;
6. PECR exception relied upon, if any; and
7. whether an objection or prior-consent control is required.

If all device storage/access is strictly necessary or validly within another statutory exception, use clear disclosure and any required objection mechanism rather than an unnecessary consent banner.

If any non-exempt technology is present, it must not operate until valid consent has been obtained.

## Child users
For under-18 users, apply the Children & Age-Appropriate Use Policy: minimise tracking, keep privacy high by default, and do not introduce behavioural advertising or unnecessary profiling.

## Change control
Reassess this document before enabling analytics, advertising, attribution, new SDKs or third-party scripts. Update the Privacy Notice where the resulting personal-data processing changes.

## Outstanding verification
Before public launch confirm:
- Turnstile's deployed browser storage/access behaviour;
- the complete set of UNLXCK local/session storage keys;
- whether analytics is enabled outside the checked repository integration; and
- whether any third-party script performs non-essential tracking.
