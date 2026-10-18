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

## Behavior

- Follow-Ups Sent 0 → 1: update the copyable DM, mark the count as synced, and write the observed follow-up date.
- Follow-Ups Sent 1 → 2: clear the DM when the formula says the sales sequence is over.
- Replied and Accepted use the existing distinct Notion formula branches. Activated uses the existing feedback prompt.
- Follow-up copy stays unchanged for Rejected/Inactive and the AI queue. The stage-history pass observes every pipeline stage, including records without Date Contacted.
- On first execution, a record with an unknown historical send date is **not assigned today's date**. The job only records dates for count increases it observes *after* baseline sync.
- The hidden server-owned field **Synced Follow-Ups Sent** distinguishes first observation from later changes. Do not manually edit it.
- Once this server job runs successfully, disable the existing Notion copy-text-sync automation so two systems do not overwrite the same field.
- Only one timer should run at a time. Errors are reported to the systemd journal and are retried at the next scheduled run.

Important: this is polling rather than an instantaneous webhook. Date recorded uses Europe/London on the day of observation (normally within two minutes), not a timestamp proven to be when the Instagram DM was sent. If a lead's count changes just before midnight and is observed after midnight, the observed date may differ from the actual send date. For exact timestamps, use a separate Mark Sent action.

## Outreach milestones and five-minute stage confirmation

The existing two-minute job now checks the **entire** pipeline for stage changes. A stage must be observed unchanged for at least five minutes before it is recorded as confirmed. Notion polling is not a perfect instant event stream: changes that occur and revert entirely between polls cannot be observed. Old records are logged as **baseline observations**, not as proof of their original change date.

- Internal fields: `Observed Stage`, `Observed Since`, `Confirmed Stage`, `Stage Confirmed At`, and `Stage History`. Leave these server-managed.
- After five-minute confirmation, existing `Replied`, `Accepted`, and `Activated` stages establish reply milestones for contacted prospects. `Accepted` or `Activated` also establishes `Accepted At`. These are the worker's **observation/confirmation times**, not invented historical Instagram DM dates. Already-confirmed baselines from #2925 with missing milestones are repaired without rewriting stage history. `Interested At` is not inferred.
- A stable observed transition to `Rejected` from a previously confirmed stage counts as a reply for contacted prospects. An initial `Rejected` baseline alone is not enough evidence. `Inactive` never implies a new reply and never erases confirmed earlier milestones.
- `Registered At`, `First Meaningful Action At`, and `Returned D7 At` are deliberately **not populated from CRM status**. Only real app-account registration and app activity can establish them.
- Headline reply/accept rates count confirmed historical milestones **or** current `Replied`/`Accepted`/`Activated` stages while existing records are baselined. This prevents false zeroes and double-counting. A later `Inactive` stage retains confirmed previous milestones.
- Activation is founder-controlled: `Stage (AI Fills First) = Activated` counts as activated immediately, using the existing contacted denominator. Neither app-event integration nor `UNLXCK_APP_EVENTS_VERIFIED` is required. Changing the stage away from `Activated` removes current activation, as before #2925.
- Notion's existing per-row stage-only reply/accept formulas can undercount confirmed historical replies after `Inactive`/`Rejected`. Use the headline cards as the conversion source of truth after successful worker sync. Per-row activation remains current-stage based.
- The separate weekly KPI database contains an `EXAMPLE — Week 1` row, not actual UNLXCK conversion data. Exclude it from real performance reporting.

Rollout: merge, deploy the updated worker, and verify the existing two-minute cron runs the new code. The headline cards recover from current CRM stages immediately; durable milestones are captured after five-minute stable observations (at most 20 stage updates per run). Verify `Stage History` and each scorecard numerator/denominator. The Notion performance page's static CRM-activation explanation was corrected on 18 October 2026; its dynamic scorecards still require the updated worker. The sync never sends an Instagram DM.

The server also checks the Notion page last-edited timestamp before confirmation. This is conservative: unrelated edits can delay confirmation, and polling still cannot prove uninterrupted stability between observations. Do not add a second scheduler: the already-installed Hetzner cron is the intended runtime.\n