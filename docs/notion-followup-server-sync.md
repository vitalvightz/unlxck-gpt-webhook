# UNLXCK Notion follow-up sync (Hetzner)

This job keeps editable **Copy Follow-Up** equal to the cold **Follow-Up DM** while Contacted, or to the warm **Warm Next DM** when a Replied/Accepted/Activated reminder is due. It never sends Instagram messages. It records **Last Follow-Up Sent** when it observes **Follow-Ups Sent** advance, which powers the existing **Actual Next Due** formula. The approved 3B scripts are selected in Python by stage and shared sequence position; cold and Activated copy retain their formula sources. The recurring job uses the already-running worker container, not a new container each time.

## One-time server setup

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

## Follow-up event history and safe Notion UX

The Notion outreach data source now has four additive properties:

- `Follow-Up 1 Sent At` and `Follow-Up 2 Sent At`: separate event times.
  Never erase either automatically; corrections require checking Instagram.
- `Safe Next Due`: the worker's materialized next eligible date/time.
- `Follow-Up Timing`: shows waiting, ready, completed or needs review.

Existing `Last Follow-Up Sent` remains only for legacy compatibility.
When a row has exactly one follow-up, the worker can copy its legacy date to
the new first-send property. When it has two, the legacy last-send value can
only populate the second-send property; the first date is **not inferred**.
Pre-existing cases without send dates remain unverified.

### Recording an action

After manually sending a DM, use the existing sent checkbox or the existing stage-specific counter once. The worker records the observation timestamp and recalculates the next due date. No new button, form, receipt field or manual date entry is required. Keep cold and warm counters separate. Both Replied and Accepted advance Signup Nudges Sent; Onboarding Nudges Sent is read-only legacy. Existing recorded timestamps are preserved; first-observed historical nonzero counters without timestamps remain unscheduled for review rather than being assigned today's date.

**One DM, one checkbox, one timestamp.** The details DM includes the signup link and getting-started instructions. Both Replied and Accepted use **Details Sent** / **Details Sent At** directly. The worker never reads or writes the retired Onboarding Sent / Onboarding Sent At properties; retain those properties and their historical values. A recorded Details Sent At is never overwritten. A newly observed unchecked→checked action timestamps the shared field once. An existing checked flag without a timestamp stays Needs Review: it is not evidence that the DM was sent today. The worker uses its existing waiting status or a query/read unchecked→checked observation as evidence of a new action; stage entry by itself is not a send event.

### Eligibility and what operators see

- Follow-up 1: three calendar days after `Date Contacted`.
- Follow-up 2: **later of** Day 8 after initial contact and 120 elapsed
  hours after the recorded first send. For a *date-only* first-send entry,
  conservatively wait until the beginning of the sixth calendar day after it.
- `Copy Follow-Up` contains the next cold message when the stage, counter and
  send-date history are valid, including before its due date.
- `Follow-Up Timing` shows waiting, ready or needs review. `Safe Next Due`
  remains the official date; an early preview is not permission to send.
- For missing dates or conflicting counters, `Copy Follow-Up` is blank and
  the reason stays in `Follow-Up Timing`.
- At two sends, `Copy Follow-Up` becomes empty and `Safe Next Due` is
  empty. Replied and Accepted have a separate automatic reminder schedule for the manual signup/onboarding check-in; no Instagram messages are ever sent automatically.
- A blank `Safe Next Due` is **correct** for terminal or blocked records;
  the `Follow-Up Timing` field explains the reason.

Use `Safe Next Due` and `Follow-Up Timing` as the two operator-facing
scheduling properties; hide the older formula-based `Actual Next Due`,
`Next Follow-Up Due`, `Follow-Up DM`, and `Next DM to Copy` from the
sending view. Those existing formulas are retained for compatibility and
may not know about the safety guard: **never send directly from them**.
The Notion `3C. MISSING SEND DATE` view isolates the historical exceptions.
Historical records with unknown send times remain blocked for review; do not assign today's date or require operators to enter dates.

### Deployment verification

The additive Notion schema changes were made before this PR was merged; the
previous worker ignores the new fields. Merge and deploy the worker before
switching the operator view from its existing `Actual Next Due` to
`Safe Next Due`. Once deployed, confirm a complete cron run and check
sample records for waiting/ready/blocked/complete states and event dates.
Disable any older Notion automation overwriting `Copy Follow-Up`.
No additional poller, Notion token, or separate scheduling service is needed.

## Warm follow-ups: automatic timestamps, no manual date fields

The existing two-minute Hetzner sync handles warm actions with no extra token, timer, or form. It preserves cold follow-ups, stage history and existing send dates. Instagram sending itself remains manual.

| Operator action after real Instagram send | Worker timestamps | Reminder |
| --- | --- | --- |
| Replied: tick **Details Sent** | Details Sent At | 3 days after signup link |
| Set **Signup Nudges Sent** 0 → 1 | Signup Nudge 1 At and Warm Last Nudge At | 4 days later |
| Set **Signup Nudges Sent** 1 → 2 | Warm Last Nudge At | Stop |
| Accepted: tick existing **Details Sent**, only if not already recorded | Details Sent At | 3 days after the combined details DM |
| Accepted: set **Signup Nudges Sent** 0 → 1 | Signup Nudge 1 At and Warm Last Nudge At | 4 days later |
| Accepted: set **Signup Nudges Sent** 1 → 2 | Warm Last Nudge At | Stop |
| Activated: tick **Feedback Requested** | Feedback Requested At | Final feedback check 5 days later |
| Tick **Feedback Reminder Sent** | Existing Warm Last Nudge At summary | Stop |

**Activated means the founder has confirmed the fighter used Unlxck**. The existing stage pass records the stage's observed date in **Observed Since** automatically. The feedback request is due four full days after that observation. Five-minute confirmation, Stage History and existing milestone/KPI calculations retain their existing definitions. The stage pass runs before scheduling, using the same worker invocation. A newly observed transition to Contacted fills a missing Date Contacted; a historical Contacted baseline does not invent a contact date.

**Safe Next Due** now materializes scheduling for Replied, Accepted and Activated as well as Contacted. Replied and Accepted both require the same recorded Details Sent At timestamp. Changing stage alone never claims a signup link or access instructions were sent. First warm reminders wait three full days; final signup/onboarding reminders wait four full days after the actual first nudge. Feedback has one reminder five full days after the first request. Completion/progression stops the relevant sequence, and the stage pass clears Safe Next Due on Rejected/Inactive/other non-follow-up stages.

Both Replied and Accepted now use Signup Nudges Sent and Synced Signup Nudges Sent only. Stage changes retain the sequence position, Signup Nudge 1 At and Warm Last Nudge At. Nonzero legacy onboarding history is held for manual reconciliation, never summed or copied into the shared counter. Legacy properties remain read-only. One first and one final nudge exhaust the sequence across both stages.

Warm intervals use elapsed UTC hours and render Europe/London timestamps across DST. Date-only historical sends wait conservatively through the last day because their time of day is unknown. Cold Day 3 / later-of-Day 8 and 120-hour rules are unchanged. Overdue reminders keep their original due dates. Invalid/missing warm counter history has no next due date. The existing synced counters are baselined while Contacted; a zero observed between the query and fresh read can establish a real first-poll 0→1. An already-nonzero first observation cannot establish its send date.

The approved SOP scripts for Replied/Accepted are mirrored independently of stale formula copy; Activated still uses its existing formula. This revision contains no RESPONSE DM reader, segment/enquiry routing, message bank, native button, receipt/state property or schema migration. Warm Last Nudge At remains the existing latest-send summary; separate signup/onboarding first-send fields are never replaced by that shared summary.

**Deploy:** after review, deploy the existing Hetzner worker and retain its current two-minute sync. No schema migration, new property or operator setup is required. Confirm a test record's observed stage date, existing sent-action timestamp and Safe Next Due together; confirm existing historical timestamps/cold dates and scorecard values remain intact. This PR does not merge or deploy itself.

**Live compatibility audit and view correction (2026-10-20):** inspection matched all 32 existing stage/action/scheduling field names and types. Views **3B. REPLIES / SIGNUP FOLLOW UPS** and **3C. ACTIVATED / FEEDBACK** now display **Safe Next Due** in the former Warm Next Due column position and sort ascending by **Safe Next Due**. Both views were fetched again after the live update; their full saved configurations matched the expected replacement, with all other columns, stage filters, names and settings preserved. Operators therefore read the exact date field written by the worker, with no separate formula/date-equivalence assumption. Warm Next Due remains an untouched legacy formula, hidden in those two views. No new property, formula change or fighter-data edit was made.

The view correction is live; the revised worker remains in unmerged PR #2972. Until that worker is deployed, warm dates can still be blank or reflect the currently deployed worker. Rollout must verify the stage/action timestamp and Safe Next Due on a test record, including waiting, overdue, complete and review states. Saved-view verification does not establish deployed worker writes or iPhone rendering.

## Accepted missing-date investigation (2026-10-20)

All six Accepted fighters identified by #2973 still have Details Sent checked, no Details Sent At, no legacy initial-send timestamp, no warm first-send timestamp and no Warm Last Nudge At. Their Notes and page bodies provide no send-time evidence; accessible comments returned no discussions. Stage History records baseline observations/confirmation (one Contacted→Accepted transition), not details-message sends. Date Added, Created/last edit, qualification timestamps, Date Contacted and cold Follow-Up 1/2/Last Follow-Up Sent timestamps do not identify the combined details DM and cannot be used as its date.

**Recovery result: 0 reliable send dates recovered from the available evidence; 6 remain unknown.** No CRM record, property, formula or view was changed during this cleanup. The worker leaves their due date empty, clears sendable copy and retains Needs Review; repeated polls or Replied→Accepted progression never silently start their countdown today. An authoritative message-send log/export could establish a date later, but this PR does not add an automatic backfill or invent historical send times.

A read-only replay of the existing 3B view's 35 records matched all 29 recorded shared-details due dates and held the six missing-date records for review. Every live Copy Follow-Up value was empty, consistent with the observed future-due/review states. The live view displays/sorts Safe Next Due and shows Details Sent rather than the retired onboarding checkbox. Positive due-message branch compatibility still requires the existing Warm Next DM and Outreach Next Step formula sources: the connector returns formula references, not the source or evaluated formula text. Do not treat mocked formula strings as live message verification; resolve this before rollout. No new template is proposed.

## Behavior

- Follow-Ups Sent 0 → 1: set the first-send timestamp only if unknown and this is a consecutive observed increase; compute the next safe due time and show WAIT until eligible.
- Follow-Ups Sent 1 → 2: preserve the first event, store the second event separately, clear the follow-up copy and safe due date.
- Replied/Accepted use new warm signup/onboarding branches, and Activated uses the feedback branch. Copy Follow-Up shows only a due sendable warm script, never operator instructions or WAIT.
- Follow-up copy stays unchanged for Rejected/Inactive and the AI queue. The stage-history pass observes every pipeline stage, including records without Date Contacted.
- On first execution, a record with an unknown historical send date is **not assigned today's date**. The job flags it in Copy Follow-Up and reports the exception count. Date/time is only recorded for *consecutive* count increases observed after baseline sync when existing event evidence is available.
- The hidden server-owned field **Synced Follow-Ups Sent** distinguishes first observation from later changes. Do not manually edit it.
- Once this server job runs successfully, disable the existing Notion copy-text-sync automation so two systems do not overwrite the same field.
- Only one timer should run at a time. Errors are reported to the systemd journal and are retried at the next scheduled run.

Important: this is polling rather than an instantaneous webhook. Date recorded uses Europe/London on the day of observation (normally within two minutes), not a timestamp proven to be when the Instagram DM was sent. If a lead's count changes just before midnight and is observed after midnight, the observed date may differ from the actual send date. The existing sent action is sufficient; do not add a separate action.

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
## Issue #3027 rollout: shared 3B sequence

This section supersedes the earlier rollout notes about independent counters and formula-owned 3B copy.

1. Test the PR, deploy its exact commit with the existing **Deploy Backend to Hetzner** workflow, and verify a successful worker health check. Keep live automatic 3B sends disabled.
2. The read-only rollout audit on 24 October found **22** signup/checkpoint mismatches across all stages (20 in Replied/Accepted), and **9** checked undated details rows in Replied/Accepted. These are current counts, not the issue's earlier snapshot. `tools/notion_warm_review.json` holds hashed page IDs for the mismatches. They receive no send timestamps or checkpoint updates, and have no warm due date or copy. Only remove an entry after manual Instagram reconciliation of counter and timestamp evidence. The nine undated rows remain blocked by the existing missing-date guard. Never reset counts or date historical sends today.
3. In the deployed worker, preview `python tools/migrate_notion_warm_counter.py`. Apply with `--apply --backup /tmp/notion-3027-formulas.json` only after reviewing the fields. Retain that backup securely outside the container. The tool revalidates schema before writing and reads back after. It makes the two warm stages use the worker's shared scheduling/copy while preserving the original cold and Activated formula branches. No fighter record is edited by the migration.
4. Verify isolated test rows at shared count 0, 1, 2, a Replied → Accepted switch, missing details/first timestamps, and historical-review states. Check Warm Next Due, Warm Next DM, Next DM to Copy and 3B Copy Follow-Up against Safe Next Due and Follow-Up Timing. Confirm a full timer run in the host journal. Mocked tests alone do not establish live formula evaluation or saved-view behavior.
5. Update the Windows Power Automate flow to use `tools/confirm_notion_warm_send.py`. Before clicking Send, call `prepare PAGE_ID STEP MESSAGE_SHA256 --journal PATH`. A successful reservation is required; duplicate reservations fail and must skip sending. After **independently confirming the actual sent message in Instagram**, call `confirm PAGE_ID STEP VERIFIED_INSTAGRAM_MESSAGE_ID --journal PATH`. Draft creation, a click, and a delay do not establish confirmation. An uncertain attempt remains held; reconcile it manually rather than preparing another send.
6. The helper revalidates stage, due date, shared counter/checkpoint, history and message hash. Confirmation patches count/checkpoint and event timestamps together. A persistent SQLite journal serializes local updates and reconciles a lost PATCH response without another increment. Keep one journal on local persistent disk, one flow instance, and one writer; Notion has no compare-and-swap API, so unrelated editors/flows must not mutate these counters during sending. This is not a distributed exactly-once guarantee across independent writers. Do not replace or delete an existing desktop attempt journal; reconcile outstanding attempts before switching helpers.
7. Deploying the repository does **not** install the helper into the local Windows flow or prove Instagram delivery confirmation. Enable automatic 3B sends only after workstation integration and the complete test-row/send-confirmation/retry flow have been verified. Activated/feedback and cold flows keep their existing handling.
