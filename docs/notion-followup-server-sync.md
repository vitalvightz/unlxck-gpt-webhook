# UNLXCK Notion follow-up sync (Hetzner)

This job keeps the editable **Copy Follow-Up** text equal to the existing **Follow-Up DM** formula. It never sends Instagram messages. It records **Last Follow-Up Sent** when it observes **Follow-Ups Sent** advance, which powers the existing **Actual Next Due** formula. No second set of DM scripts is hardcoded in Python. The recurring job uses the already-running worker container, not a new container each time.

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

### Sending and Notion button configuration

A **Notion button must be configured manually**; this PR does not create it.
For reliability, two explicit actions are preferable to a dynamic counter:

1. On the pipeline database, create buttons `Sent follow-up 1` and
   `Sent follow-up 2`, and show them only in an operator view (the buttons
   are not hard access controls). Each has a confirmation action.
2. `Sent follow-up 1` updates `Follow-Ups Sent = 1`,
   `Follow-Up 1 Sent At = Now`, and `Last Follow-Up Sent = Now`.
   `Sent follow-up 2` updates `Follow-Ups Sent = 2`,
   `Follow-Up 2 Sent At = Now`, and `Last Follow-Up Sent = Now`.
3. **Only click after the corresponding Instagram DM was actually sent.**
   Do not use the buttons if `Follow-Up Timing` is not `...: ready`.
   The button does not send Instagram messages or enforce eligibility itself.
4. Never click the same follow-up button twice. Test both actions on a test
   record, then verify the individual timestamps and `Safe Next Due`.

The worker preserves explicitly provided event times. On a legacy dropdown
change, it records the time **the poll observed the increase** instead,
normally within two minutes, without pretending that is the Instagram send
time. A missed 0 → 2 jump is flagged, never backfilled with fabricated times.
A reversed count retains both history fields and raises a review status.

### Eligibility and what operators see

- Follow-up 1: three calendar days after `Date Contacted`.
- Follow-up 2: **later of** Day 8 after initial contact and 120 elapsed
  hours after the recorded first send. For a *date-only* first-send entry,
  conservatively wait until the beginning of the sixth calendar day after it.
- If not yet eligible, `Copy Follow-Up` says **WAIT**; it contains no
  sendable script. If the date is missing or the counter conflicts with
  history, it says **NEEDS DATE** or **NEEDS REVIEW**.
- Once eligible, `Copy Follow-Up` contains the existing calculated DM.
- At two sends, `Copy Follow-Up` becomes empty and `Safe Next Due` is
  empty. Replied and Accepted use their existing distinct response templates;
  there is no automatic outbound follow-up due.
- A blank `Safe Next Due` is **correct** for terminal or blocked records;
  the `Follow-Up Timing` field explains the reason.

Use `Safe Next Due` and `Follow-Up Timing` as the two operator-facing
scheduling properties; hide the older formula-based `Actual Next Due`,
`Next Follow-Up Due`, `Follow-Up DM`, and `Next DM to Copy` from the
sending view. Those existing formulas are retained for compatibility and
may not know about the safety guard: **never send directly from them**.
The Notion `3C. MISSING SEND DATE` view isolates the historical exceptions.
Verify each first-send date against Instagram and fill in
`Follow-Up 1 Sent At` (or legacy `Last Follow-Up Sent` while still at
count 1), rather than assigning today's date.

### Deployment verification

The additive Notion schema changes were made before this PR was merged; the
previous worker ignores the new fields. Merge and deploy the worker before
switching the operator view from its existing `Actual Next Due` to
`Safe Next Due`. Once deployed, confirm a complete cron run and check
sample records for waiting/ready/blocked/complete states and event dates.
Disable any older Notion automation overwriting `Copy Follow-Up`.
No additional poller, Notion token, or separate scheduling service is needed.

## Behavior

- Follow-Ups Sent 0 → 1: set the first-send timestamp only if unknown and this is a consecutive observed increase; compute the next safe due time and show WAIT until eligible.
- Follow-Ups Sent 1 → 2: preserve the first event, store the second event separately, clear the follow-up copy and safe due date.
- Replied and Accepted use the existing distinct Notion formula branches. Activated uses the existing feedback prompt.
- Follow-up copy stays unchanged for Rejected/Inactive and the AI queue. The stage-history pass observes every pipeline stage, including records without Date Contacted.
- On first execution, a record with an unknown historical send date is **not assigned today's date**. The job flags it in Copy Follow-Up and reports the exception count. Date/time is only recorded for *consecutive* count increases observed after baseline sync unless a Notion button supplied the event time.
- The hidden server-owned field **Synced Follow-Ups Sent** distinguishes first observation from later changes. Do not manually edit it.
- Once this server job runs successfully, disable the existing Notion copy-text-sync automation so two systems do not overwrite the same field.
- Only one timer should run at a time. Errors are reported to the systemd journal and are retried at the next scheduled run.

Important: this is polling rather than an instantaneous webhook. Date recorded uses Europe/London on the day of observation (normally within two minutes), not a timestamp proven to be when the Instagram DM was sent. If a lead's count changes just before midnight and is observed after midnight, the observed date may differ from the actual send date. For exact timestamps, use a separate Mark Sent action.

## Outreach milestones and five-minute stage confirmation

The existing two-minute job now checks the **entire** pipeline for stage changes. A stage must be observed unchanged for at least five minutes before it is recorded as confirmed. Notion polling is not a perfect instant event stream: changes that occur and revert entirely between polls cannot be observed. Old records are logged as **baseline observations**, not as proof of their original change date.

- Internal fields: `Observed Stage`, `Observed Since`, `Confirmed Stage`, `Stage Confirmed At`, and `Stage History`. Leave these server-managed.
- After five-minute confirmation, existing `Replied`, `Accepted`, and `Activated` stages establish reply milestones for contacted prospects. `Accepted` or `Activated` also establishes `Accepted At`. These are the worker's **observation/confirmation times**, not invented historical Instagram DM dates. Already-confirmed baselines from #2925 with missing milestones are repaired without rewriting stage history. `Interested At` is not inferred.
- A stable observed transition to `Rejected` from a previously confirmed stage records a durable reply milestone for contacted prospects. The scorecard counts current `Rejected` immediately, without waiting for stage confirmation; an initial `Rejected` baseline does not fabricate a historical reply timestamp. `Inactive` never implies a new reply and never erases confirmed earlier milestones.
- `Registered At`, `First Meaningful Action At`, and `Returned D7 At` are deliberately **not populated from CRM status**. Only real app-account registration and app activity can establish them.
- Headline reply rate counts confirmed historical milestones **or** current `Replied`/`Accepted`/`Activated`/`Rejected` stages for contacted prospects. Acceptance counts confirmed milestones **or** current `Accepted`/`Activated`. Each fighter counts once per rate, including when a current stage and prior milestone both match. A later `Inactive` stage retains confirmed previous milestones.
- Activation is founder-controlled: `Stage (AI Fills First) = Activated` counts as activated immediately, using the existing contacted denominator. Neither app-event integration nor `UNLXCK_APP_EVENTS_VERIFIED` is required. Changing the stage away from `Activated` removes current activation, as before #2925.
- Notion's existing per-row stage-only reply/accept formulas can undercount confirmed historical replies after `Inactive`/`Rejected`. Use the headline cards as the conversion source of truth after successful worker sync. Per-row activation remains current-stage based.
- The separate weekly KPI database contains an `EXAMPLE — Week 1` row, not actual UNLXCK conversion data. Exclude it from real performance reporting.

Rollout: merge, deploy the updated worker, and verify the existing two-minute cron runs the new code. The headline cards recover from current CRM stages immediately; durable milestones are captured after five-minute stable observations (at most 20 stage updates per run). Verify `Stage History` and each scorecard numerator/denominator. The Notion performance page's static CRM-activation explanation was corrected on 18 October 2026; its dynamic scorecards still require the updated worker. The sync never sends an Instagram DM.

The server also checks the Notion page last-edited timestamp before confirmation. This is conservative: unrelated edits can delay confirmation, and polling still cannot prove uninterrupted stability between observations. Do not add a second scheduler: the already-installed Hetzner cron is the intended runtime.\n