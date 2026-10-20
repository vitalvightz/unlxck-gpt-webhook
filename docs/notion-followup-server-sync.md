# UNLXCK Notion follow-up sync (Hetzner)

The existing two-minute Hetzner job records manual outreach actions and materializes **Copy Follow-Up**, **Safe Next Due** and **Follow-Up Timing**. It never sends Instagram messages. Cold, signup and onboarding counters/history remain independent. **Activated means the founder has confirmed the fighter has used Unlxck**, not merely signed up.

## Operator workflow

1. Change the fighter's stage.
2. Read the next action and copy the approved DM from **Copy Follow-Up** on iPhone; send it manually.
3. Click **Record Send** once. The worker updates the existing checkbox/counter and send timestamps. Do not also increment a counter for the same send.

After bootstrap, the existing **Details Sent**, **Onboarding Sent**, **Feedback Requested**, **Feedback Reminder Sent** checkboxes and existing nudge counters remain supported as alternative single actions. They record the worker's observation time. The recommended button also works before the first worker baseline because it supplies an explicit action receipt. No operator dates or forms are needed.

**Copy Follow-Up contains only eligible DM text.** Waiting, blocked, completed, rejected and inactive rows have an empty copy field. Timing/review instructions live in **Follow-Up Timing**, not in the DM. In the existing warm views, **Outreach Next Step** mirrors that status, **Warm Next Due** mirrors Safe Next Due and **Warm Next DM** mirrors the copy field. Do not send from older cold estimate/formula fields.

For Replied, the states are: reply received / send details; details sent / waiting for signup; first follow-up due; final follow-up due; completed or progressed. Entering Replied does not imply a link was sent. The initial response comes from the existing [RESPONSE DM](https://www.notion.so/3fbd6e718d27803cbd94fe94f19a002a) page. General replies use the segment's recommended response; explicit enquiry cues in existing Notes/Objection can select the approved coaching, conditioning, timer or recovery response. All eight alternatives remain available on that page. Check the conversation and choose a matching response before sending. Accepted initial access instructions remain a manual approved response; tick Onboarding Sent after sending them.

## Scheduling and history

| Stage/action | Next action |
| --- | --- |
| Contacted, zero cold sends | First cold follow-up on calendar Day 3 in Europe/London |
| Contacted, one cold send | Second cold follow-up at the later of calendar Day 8 and 120 elapsed hours after first send |
| Replied, details/link actually sent | First signup nudge after 72 elapsed hours |
| Replied, first signup nudge sent | Final signup nudge after 96 elapsed hours; stop after two |
| Accepted, instructions actually sent | First onboarding nudge after 72 elapsed hours |
| Accepted, first onboarding nudge sent | Final onboarding nudge after 96 elapsed hours; stop after two |
| Activated, founder-confirmed use observed | Feedback request after 96 elapsed hours |
| Feedback requested | One reminder after 120 elapsed hours; stop thereafter |

Timestamp arithmetic uses UTC elapsed hours and renders Europe/London with DST. Cold Day 3/Day 8 retain their original London calendar-day rules. A date-only historical action has unknown time of day: wait through the whole final day (e.g. a three-day wait becomes midnight at the start of day four). Overdue messages remain eligible; time passing never increments a send counter.

The worker baselines every non-system prospect, including Ready to Send, so stage entry cannot consume the first warm counter increment. It also checks for actions between the query and fresh read. A 0→1 transition with an established zero baseline records its observed time, even when the stage subsequently progresses. Existing verified event timestamps are retained. A plain nonzero counter already present on the very first observation cannot establish a send time: **Needs Review**, never today’s invented timestamp. The Record Send receipt resolves this ambiguity for new actions.

0→2, reversals, missing roots/first/final timestamps, changed verified dates, impossible timing, malformed receipts and conflicting sends block that stage. Review latches survive retries and stage exits/re-entry. A duplicate delivery of the same receipt is idempotent; another receipt for an already recorded action is blocked. Two sends never generate a third message. Confirmed registration stops signup nudges; Onboarding Complete stops onboarding nudges; Feedback Submitted stops feedback requests/reminders. Stage progression stops the previous sequence; Rejected/Inactive/Review Hold clear outbound copy.

**Historical exceptions are not routine operator work.** A maintainer must verify the conversation/evidence, repair the existing canonical fields if evidence exists and clear only that stage's review entry in Follow-Up Sync State after reviewing the evidence. Do not reset whole state, zero counters, clear receipt deduplication or assign today's date. If send time is unknowable, leave the row blocked or move it to Inactive. New sends require one action, not historical reconstruction.

## One-time compatibility migration (after PR review)

The corrective PR does not change the live workspace or deploy itself. Use the existing worker image/token, not a new integration.

1. Pause the existing timer during migration/bootstrap; retain its two-minute schedule. Disable any old Notion automation that writes Copy Follow-Up. Keep a schema export for rollback.
2. Preview the exact live schema/formula changes with:

   ```sh
   docker compose exec -T worker python tools/sync_notion_followups.py --schema-plan
   ```

3. Review the preview, then apply it with `--prepare-schema`. This adds two hidden text properties, **Follow-Up Sync State** (baselines, separate warm final-send evidence, immutable date snapshots and review latches) and **Follow-Up Send Receipt** (one button request, deduplicated in state). These are essential: the existing shared Warm Last Nudge At cannot retain independent signup/onboarding final-send evidence, and a counter alone cannot distinguish a historical value from a newly recorded pre-baseline send. Neither is a duplicate counter or external datastore.
4. The same migration makes Warm Next Due = `prop("Safe Next Due")`, Warm Next DM = `prop("Copy Follow-Up")`, and wraps the existing Outreach Next Step expression with a warm-stage Timing branch, preserving the complete original non-warm expression. Existing view names, filters, sorts and displayed warm fields continue working. Cold Follow-Up DM, Actual Next Due, stage history and KPI formulas are untouched. The migration is idempotent and rejects incompatible property types before any writes.
5. Grant the existing worker integration read access to RESPONSE DM if it does not already have it (reuse the same token). Configure the native **Record Send** database button below, then run `--check-schema`. That read-only check verifies property types, the bridge formulas and all approved RESPONSE DM section boundaries using the existing REST token.
6. Bootstrap once using the usual command. Historical exceptions should become Needs Review, with no fabricated send dates. A first full baseline may exceed two minutes; the lock prevents overlap. Resume the same timer.
7. Test with a clearly marked non-production prospect: initial response, details recorded, signup 0→1, onboarding independently, feedback request/reminder, waiting/overdue/completed/rejected and a counter reversal. Check individual event dates, next date/action, selectable iPhone copy and the existing stage/KPI passes. Do not send real test DMs. Confirm the entire cron run in the journal.

The live connector audit on 2026-10-20 verified existing property names/types, the 3/3B/3C views, milestone/scorecard documentation and approved RESPONSE DM content. It exposes formulaCode references but cannot retrieve formula source or evaluate formulaResult references. **Live formula source, migration writes, native button execution, iPhone behavior and Hetzner deployment remain unverified until the above checks run.** Unit tests do not establish live integration success.

### Record Send button

Create one database Button property named **Record Send** and show it in sending views. Its only Edit pages action targets **This page** and sets **Follow-Up Send Receipt** using the following custom formula. Insert the native **This page** property references with Notion's formula picker where needed; the expression below uses the ordinary `prop(...)` notation to describe those references. The button records the stage/action at click time, so a later stage change cannot relabel it. It sends no Instagram message.

```text
lets(
  s, prop("Stage (AI Fills First)"),
  a, ifs(
    s == "Contacted", format(toNumber(prop("Follow-Ups Sent")) + 1),
    s == "Replied", if(prop("Details Sent"), format(toNumber(prop("Signup Nudges Sent")) + 1), "initial"),
    s == "Accepted", if(prop("Onboarding Sent"), format(toNumber(prop("Onboarding Nudges Sent")) + 1), "initial"),
    s == "Activated", if(prop("Feedback Requested"), "reminder", "request"),
    "blocked"
  ),
  s + "|" + a + "|" + formatDate(now(), "YYYY-MM-DDTHH:mm:ssZ")
)
```

Example receipt: `Replied|1|2026-10-20T20:00:00+01:00`. Click only after the actual DM and while the displayed action is ready. Before the first baseline, an initial response can be copied directly from RESPONSE DM and recorded with the same button. The worker independently rejects unknown/early/skipped/duplicate actions; it never overwrites a verified event date. Do not combine the button with a checkbox/counter change. Native button configuration is a one-time maintainer setup; the API schema migration cannot configure Notion buttons.

## Concurrency and operational limits

The existing worker uses a nonblocking Linux flock across follow-ups, stage history and scorecards. Keep every invocation in that same worker/container and never delete the lock file while it may be held. It is not a distributed lock for multiple hosts; no second worker is supported. Stable baselined rows use no per-row API reads/writes, preserving normal polling capacity. Changed rows get fresh reads and a final full-property/revision comparison before writing. Mutating requests are not blindly retried on rate limits/server errors; the next poll reads current state and resumes.

Notion does not offer a conditional page PATCH. An edit in the narrow interval after the final GET remains possible; this implementation cannot promise transactional isolation from human edits. The worker never patches operator fields except when consuming an explicit Record Send receipt. Do not edit/click a row again while a receipt is pending; wait for the copy/action to refresh. Stage changes that occur and revert entirely between polls are unobservable. New in-stage Instagram replies/engagement are not available to this worker: the operator must progress the stage or select Inactive when follow-ups should stop. No Instagram/app-event integration is added.

Approved copy is read from RESPONSE DM every run, identified by section metadata, not greeting text. Removing/renaming those section labels blocks warm copying until repaired; editing message wording does not affect eligibility. If that page is inaccessible or malformed, warm copy clears with Needs Review while cold/history/KPI work can continue. The test fixture is an audited page snapshot for parser regression only; runtime never uses it as a second message bank.

## Original server setup reference

If the two-minute Hetzner timer is already running, keep it; do not create a second timer or service. For an existing installation, use the compatibility migration above. This section documents the original installation only.

1. **Reuse the existing outreach AI qualification integration.** The qualification worker already polls and writes the same UNLXCK Beta Candidate Pipeline every ~2 minutes, so do not make a new Notion integration or issue a second token. Check that its integration can update `Copy Follow-Up`, `Synced Follow-Ups Sent`, and `Last Follow-Up Sent`.
2. Check where that existing secret is injected. This script recognises `NOTION_TOKEN`, `NOTION_API_KEY`, or `NOTION_INTEGRATION_TOKEN` in its own process. If the qualification worker and Unlxck Docker worker already share one of these environment variables, no credential change is needed. **If the qualification worker is a separate service, the Docker worker does not automatically inherit its environment**: securely expose the *existing* token to the Docker worker via `/opt/unlxck/.env.production` or invoke this script from the existing qualification worker instead. Never print or commit the secret. The data source ID already points at the current pipeline; optionally set `NOTION_OUTREACH_DATA_SOURCE_ID`.
3. Merge this pull request only once checks have passed. Wait until the usual Hetzner backend deployment has built the new worker image. Prefer scheduling this job alongside the **existing outreach qualification poll** if its source/service is available, to avoid an unnecessary second Notion poll. Otherwise use the timer below.
4. Run once from /opt/unlxck to confirm that the **existing token is accessible within this container** and that writes succeed. Stop if it fails; do not generate a second token as a workaround:

    docker compose exec -T worker python tools/sync_notion_followups.py

5. Use a systemd timer to run every two minutes. Create /etc/systemd/system/unlxck-notion-followups.service:

    [Unit]
    Description=Sync UNLXCK Notion follow-ups
    [Service]
    Type=oneshot
    WorkingDirectory=/opt/unlxck
    ExecStart=/usr/bin/docker compose exec -T worker python tools/sync_notion_followups.py

6. Create /etc/systemd/system/unlxck-notion-followups.timer:

    [Unit]
    Description=Sync UNLXCK follow-ups every two minutes
    [Timer]
    OnCalendar=*:0/2
    Persistent=true
    Unit=unlxck-notion-followups.service
    [Install]
    WantedBy=timers.target

7. Start the timer and check logs:

    sudo systemctl daemon-reload
    sudo systemctl enable --now unlxck-notion-followups.timer
    systemctl list-timers unlxck-notion-followups.timer
    sudo journalctl -u unlxck-notion-followups.service -n 30 --no-pager

The systemd timer lives on the host and calls the running worker. A run may fail while the worker restarts during backend deployment; the next scheduled run will retry. Confirm Docker is installed at /usr/bin/docker; replace that path if necessary.

## Outreach milestones and five-minute stage confirmation

The existing two-minute job now checks the **entire** pipeline for stage changes. A stage must be observed unchanged for at least five minutes before it is recorded as confirmed. Notion polling is not a perfect instant event stream: changes that occur and revert entirely between polls cannot be observed. Old records are logged as **baseline observations**, not as proof of their original change date.

- Internal fields: `Observed Stage`, `Observed Since`, `Confirmed Stage`, `Stage Confirmed At`, and `Stage History`. Leave these server-managed.
- After five-minute confirmation, existing `Replied`, `Accepted`, and `Activated` stages establish reply milestones for contacted prospects. `Accepted` or `Activated` also establishes `Accepted At`. These are the worker's **observation/confirmation times**, not invented historical Instagram DM dates. Already-confirmed baselines from #2925 with missing milestones are repaired without rewriting stage history. `Interested At` is not inferred.
- A stable observed transition to `Rejected` from a previously confirmed stage records a durable reply milestone for contacted prospects. The scorecard counts current `Rejected` immediately, without waiting for stage confirmation; an initial `Rejected` baseline does not fabricate a historical reply timestamp. `Inactive` never implies a new reply and never erases confirmed earlier milestones.
- `Registered At`, `First Meaningful Action At`, and `Returned D7 At` are deliberately **not populated from CRM status**. Only real app-account registration and app activity can establish them.
- Headline reply rate counts confirmed historical milestones **or** current `Replied`/`Accepted`/`Activated`/`Rejected` stages for contacted prospects. Acceptance counts confirmed milestones **or** current `Accepted`/`Activated`. Each fighter counts once per rate, including when a current stage and prior milestone both match. A later `Inactive` stage retains confirmed previous milestones.
- Activation is founder-controlled: the founder sets `Stage (AI Fills First) = Activated` only after confirming the fighter **used the app**. The CRM counts the stage immediately, using the existing contacted denominator. Neither app-event integration nor `UNLXCK_APP_EVENTS_VERIFIED` is required. Changing the stage away from `Activated` removes current activation, as before #2925.
- Notion's existing per-row stage-only reply/accept formulas can undercount confirmed historical replies after `Inactive`/`Rejected`. Use the headline cards as the conversion source of truth after successful worker sync. Per-row activation remains current-stage based.
- The separate weekly KPI database contains an `EXAMPLE — Week 1` row, not actual UNLXCK conversion data. Exclude it from real performance reporting.

Rollout: merge, deploy the updated worker, and verify the existing two-minute cron runs the new code. The headline cards recover from current CRM stages immediately; durable milestones are captured after five-minute stable observations (at most 20 stage updates per run). Verify `Stage History` and each scorecard numerator/denominator. The Notion performance page's static CRM-activation explanation was corrected on 18 October 2026; its dynamic scorecards still require the updated worker. The sync never sends an Instagram DM.

The server also checks the Notion page last-edited timestamp before confirmation. This is conservative: unrelated edits can delay confirmation, and polling still cannot prove uninterrupted stability between observations. Do not add a second scheduler: the already-installed Hetzner cron is the intended runtime.\n