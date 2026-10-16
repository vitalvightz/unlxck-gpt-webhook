# UNLXCK Notion follow-up sync (Hetzner)

This job keeps the editable **Copy Follow-Up** text equal to the existing **Follow-Up DM** formula. It never sends Instagram messages. It records **Last Follow-Up Sent** when it observes **Follow-Ups Sent** advance, which powers the existing **Actual Next Due** formula. No second set of DM scripts is hardcoded in Python. The recurring job uses the already-running worker container, not a new container each time.

## One-time server setup

1. Give a Notion integration read/write access to the existing UNLXCK Beta Candidate Pipeline.
2. On Hetzner add NOTION_TOKEN=your_notion_integration_token to /opt/unlxck/.env.production, privately. Do not commit or print the token. The script already defaults to the correct current data source ID; optionally set NOTION_OUTREACH_DATA_SOURCE_ID.
3. Merge this pull request and wait until the usual Hetzner backend deployment has built the new worker image.
4. Run once from /opt/unlxck to confirm permission and initial sync:

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
- No changes are made to Rejected/Inactive or the AI queue.
- On first execution, a record with an unknown historical send date is **not assigned today's date**. The job only records dates for count increases it observes *after* baseline sync.
- The hidden server-owned field **Synced Follow-Ups Sent** distinguishes first observation from later changes. Do not manually edit it.
- Once this server job runs successfully, disable the existing Notion copy-text-sync automation so two systems do not overwrite the same field.
- Only one timer should run at a time. Errors are reported to the systemd journal and are retried at the next scheduled run.

Important: this is polling rather than an instantaneous webhook. Date recorded uses Europe/London on the day of observation (normally within two minutes), not a timestamp proven to be when the Instagram DM was sent. If a lead's count changes just before midnight and is observed after midnight, the observed date may differ from the actual send date. For exact timestamps, use a separate Mark Sent action.
