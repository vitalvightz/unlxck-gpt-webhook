# UNLXCK Data Retention, Deletion & User Rights Policy

## Purpose
UNLXCK keeps identifiable personal data only for as long as needed for the purpose it was collected for. Data must then be deleted or irreversibly anonymised unless a legal or operational reason justifies further retention.

## Retention Schedule

Four distinct events end retention, and they are not interchangeable. Collapsing them was the previous schedule's weakness: "review on account closure" is a trigger, not a period, and leaves data in place indefinitely if the review never happens.

| Event | Meaning |
|---|---|
| **Active** | Account open and in use |
| **Dormant** | No sign-in for 24 months |
| **Closed** | Athlete stopped using UNLXCK and closed the account |
| **Erasure request** | Athlete exercised the Article 17 right |

| Data | Active | Dormant (24m no sign-in) | Closed | Erasure request |
|---|---|---|---|---|
| Account/profile | Retained | Contact, then delete if no return | Delete after 90 days | Delete within 30 days |
| Injury, pain, readiness, recovery | Retained | Delete | Delete after 90 days | Delete within 30 days |
| Nutrition/bodyweight | Retained | Delete | Delete after 90 days | Delete within 30 days |
| Intake, plans, training/session history | Retained | Anonymise | Anonymise after 24 months | Delete within 30 days |
| Feedback | While needed for support/improvement, then anonymise or delete | — | — | Delete or anonymise within 30 days |
| Beta screenshots | Maximum 90 days — enforced in `api/services/feedback_service.py` | — | — | Delete within 30 days |
| Security/audit logs | 90 days | — | — | Retained where the security purpose justifies it; record the reason |
| Backups | Removed through the applicable backup expiry cycle; deleted data must not be restored into active processing except where necessary for recovery |

**Why closure and erasure differ.** Closing an account is not the same as asking to be erased. A 90-day grace period after closure lets an athlete come back without losing their history, and the 24-month anonymisation window reflects that athletes return after breaks. An *erasure request* carries no such grace: Article 17 requires deletion without undue delay, and holding special-category health data for 90 days after someone has asked for it to go is not defensible. When in doubt, treat the request as erasure.

**Anonymisation means irreversible.** Training history retained past the health-data deletion point must be stripped of identifiers so it cannot be linked back to the athlete. If it can be re-linked, it is still personal data and the retention period has not been honoured.

## Implementation status

> **These periods are published in the Privacy Notice but are not yet automated.** Only screenshot retention is enforced in code. Until scheduled deletion exists, the periods above are met by manual action, which means they can be missed — and a specific published period that is missed is a worse position than the vague wording it replaced, because the promise is now precise.
>
> Required: scheduled jobs for dormancy detection and notification, post-closure health deletion at 90 days, training-history anonymisation at 24 months, and audit-log expiry at 90 days. Until those exist, run the schedule manually on a recorded cadence and log each run.

UNLXCK must not retain data indefinitely "just in case".

## User Rights
UNLXCK must support applicable UK data-protection rights, including:

- access to personal data;
- correction of inaccurate data;
- erasure where the right applies;
- restriction of processing where the right applies;
- data portability where applicable;
- objection where applicable; and
- withdrawal of consent for processing based on consent.

Requests may be made through the published privacy contact route. Identity may be verified where reasonably necessary.

## Response Procedure
1. Record the request and date received.
2. Verify identity only where necessary.
3. Identify all relevant UNLXCK systems and processors.
4. Apply any required restriction while the request is assessed.
5. Complete the request without undue delay and within the applicable legal deadline.
6. Record the outcome and any lawful reason for data retained or a request refused.

Subject-access requests should normally be completed within one calendar month. Any lawful extension or refusal must be communicated as required by UK data-protection law.

## Account Deletion
A valid deletion request must trigger review/removal of the user's identifiable data across active UNLXCK systems and relevant processors. Data that must lawfully remain must be minimised, isolated from ordinary product use and retained only for the justified purpose.

Deletion from backups may follow the documented backup lifecycle where immediate physical deletion is impracticable, but deleted information must not return to ordinary active processing.

## Ownership and Review
UNLXCK is responsible for maintaining this schedule, implementing deletion controls and periodically reviewing retained data. New data categories or processors require a retention decision before release.

## Launch Requirement
Before public launch, UNLXCK must:

- publish a working route for privacy/data-rights requests;
- replace the Settings statement that export/deletion controls are only available after launch;
- define operational retention periods for logs and other categories currently without one; and
- test account deletion and data retrieval across all relevant systems/processors.
