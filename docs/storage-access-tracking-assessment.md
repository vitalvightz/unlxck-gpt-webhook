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

| Technology / use | Likely purpose | Initial position |
|---|---|---|
| Supabase authentication/session storage | Sign-in and account security | Likely strictly necessary; no PECR consent if limited to this purpose |
| UNLXCK appearance preference/local storage | Remember dark/light or similar user preference | May fall within the appearance exception; disclose and provide objection control where required |
| Private-trial / app state storage required to operate requested features | Service operation | Assess individually; strictly necessary use may not require consent |
| Cloudflare Turnstile | Authentication abuse/bot prevention | Likely security/service necessity, but verify exact storage/access behaviour and disclosure requirements |
| Sentry | Error/performance monitoring | Verify SDK configuration, identifiers, cookies/local storage and whether use can meet an applicable exception; otherwise consent before non-essential storage/access |
| Vercel platform logs/hosting | Server-side request/technical logs | PECR consent generally concerns storage/access on the user's device; separately disclose personal-data processing where applicable |
| Vercel Analytics or other analytics, if enabled | Product usage measurement | Verify whether enabled and whether implementation satisfies the UK statistical-purpose exception; if not, obtain consent |
| Advertising pixels / behavioural tracking | Advertising/profiling | No such tool should be added without prior compliance review; normally expect consent |
| Push subscription/browser notification data | Deliver notifications requested by the user | Permission/consent flow is handled by browser/platform; assess any additional device storage separately |

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

If all device storage/access is strictly necessary or validly within another statutory exception, use clear disclosure and the required objection mechanisms rather than an unnecessary consent banner.

If any non-exempt technology is present, it must not operate until valid consent has been obtained.

## Child users
For under-18 users, apply the Children & Age-Appropriate Use Policy: minimise tracking, keep privacy high by default, and do not introduce behavioural advertising or unnecessary profiling.

## Change control
Reassess this document before enabling analytics, advertising, attribution, new SDKs or third-party scripts. Update the Privacy Notice where the resulting personal-data processing changes.

## Outstanding verification
Before public launch confirm:
- whether Vercel Analytics or any equivalent analytics is enabled;
- Sentry's exact browser storage/access behaviour and event payload;
- Turnstile's current storage/access behaviour;
- the complete set of UNLXCK local/session storage keys; and
- whether any third-party script performs non-essential tracking.
