# UNLXCK Data Map & Processor Register

## Purpose
Internal record of the main personal-data flows used by UNLXCK. Keep this aligned with production code and the Privacy Notice.

## Data map

| Data | Purpose | Sensitivity | Main location / recipient | Access | Retention |
|---|---|---|---|---|---|
| Account data: name, email, username, role, profile settings | Authentication and account operation | Personal data | Supabase Auth/Postgres | Athlete; authorised backend/admin | Define before public launch |
| Athlete profile: age, sex, height, weight, sport/style, schedule, goals | Personalise training and nutrition | Personal; some fields may contribute to health inferences | Supabase/Postgres; plan-generation pipeline | Athlete; authorised backend/admin | Define before public launch |
| Injury and symptom data: area, severity, trend, wound/infection signals, notes, restrictions | Adapt or restrict training and trigger safety escalation | **Special-category health data** | Supabase/Postgres; backend injury engine; relevant context may enter plan generation | Athlete; authorised backend/admin | Define before public launch |
| Readiness/recovery: soreness, fatigue, sleep, readiness, injury notes | Daily training adaptation | **Special-category health data where it reveals health status** | Supabase/Postgres; recommendation engine | Athlete; authorised backend/admin | Define before public launch |
| Training/session data: completion, RPE, duration, notes | Progress tracking and adaptation | Personal; may reveal health/performance information | Supabase/Postgres | Athlete; authorised backend/admin | Define before public launch |
| Nutrition/weight-cut data: bodyweight, target weight, appetite, supplements/caffeine, weight-cut risk | Nutrition and fight-camp guidance | Personal; may constitute/infer health data depending on use | Supabase/Postgres; application logic | Athlete; authorised backend/admin | Define before public launch |
| Plans and adaptation decisions | Deliver personalised programme and explain changes | Personal; may contain health-derived recommendations | Supabase/Postgres; OpenAI for Stage 2 plan finalisation | Athlete; authorised backend/admin | Define before public launch |
| Beta feedback and screenshots | Product QA and support | Personal; screenshot may contain sensitive app information | Supabase private storage/Postgres; Resend notification where enabled | Authorised admins | Screenshots: 90 days; define feedback-record retention |
| Push subscription, timezone and training-time data | Deliver training/safety notifications at appropriate times | Personal/device data | Supabase/Postgres; web-push infrastructure | Athlete; authorised backend | Define before public launch |
| Security/diagnostic events | Reliability, abuse prevention and incident investigation | Technical/personal data | Sentry and server logs; Cloudflare Turnstile for anti-abuse at auth | Authorised operations; relevant processor | Define before public launch |

## Processor / service register

| Service | Role in UNLXCK | Data potentially processed | Status before launch |
|---|---|---|---|
| **Supabase** | Authentication, PostgreSQL database, private storage | Account, profile, training, health/injury, nutrition, plans, feedback | Verify DPA, region, subprocessors, retention/deletion behaviour |
| **OpenAI** | Stage 2 plan finalisation / structured plan generation | Plan-generation context, potentially including injury/restriction information | Confirm exact payload, contractual data controls, retention and transfer position |
| **Vercel** | Next.js web hosting / routing | Request, device and technical metadata | Verify logs, analytics if enabled, region and retention |
| **Hetzner** | Production API and generation worker hosting | Data processed by backend/worker in transit and memory; server logs | Document server location, backups and log retention |
| **Sentry** | Error/performance monitoring | Technical events; possible user/context metadata | `sendDefaultPii` is disabled; verify event payloads and retention |
| **Resend** | Beta-feedback notification email | Privacy-minimised feedback notification data when enabled | Confirm exact fields, retention and DPA |
| **Cloudflare Turnstile** | Signup/login abuse prevention | Device/network/security-challenge information | Document disclosure and applicable device-storage/PECR position |

## Controller position
UNLXCK determines why and how athlete data is processed for the service and should treat itself as the controller for these core processing activities. External services acting on UNLXCK's instructions should be assessed and contracted as processors where appropriate.

## Rules
- Health and health-inference data must be clearly identified in the Privacy Notice and lawful-basis/DPIA work.
- Do not add a new third-party recipient or materially new data use without updating this register.
- Do not send more athlete data to an external service than the function requires.
- Retention periods marked "Define before public launch" must be resolved in the Retention & Deletion Policy.
- International-transfer mechanisms, processor contracts and subprocessors must be verified before public launch.

## Next dependency
Use this register to complete the **Health Data Lawful-Basis Assessment and DPIA**. It is not a substitute for the Privacy Notice or Article 30 record where further detail is required.
