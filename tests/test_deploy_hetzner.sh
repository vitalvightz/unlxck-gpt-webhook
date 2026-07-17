#!/usr/bin/env bash

set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/deploy_hetzner.sh
source "$REPO_ROOT/scripts/deploy_hetzner.sh"

TEST_ROOT="$(mktemp -d)"
COMMAND_LOG="$TEST_ROOT/commands.log"
REPORT_LOG="$TEST_ROOT/report.log"
trap 'rm -rf "$TEST_ROOT"' EXIT

git() {
    printf 'git %s\n' "$*" >> "$COMMAND_LOG"
}

docker() {
    printf 'docker %s\n' "$*" >> "$COMMAND_LOG"
    if [[ "${1:-}" == "ps" && "${2:-}" == "-q" ]]; then
        printf 'worker-container'
    fi
}

wait_for_api_health() {
    printf 'wait_for_api_health %s\n' "$*" >> "$COMMAND_LOG"
    API_HEALTH_RESULT="container_healthy"
}

verify_worker() {
    printf 'verify_worker\n' >> "$COMMAND_LOG"
}

verify_public_health() {
    printf 'verify_public_health\n' >> "$COMMAND_LOG"
    API_HEALTH_RESULT="http_200"
}

container_state() {
    printf 'running'
}

DEPLOY_ROOT="$TEST_ROOT"
PREVIOUS_SHA="1111111111111111111111111111111111111111"
DEPLOYED_SHA="unknown"
CADDY_CHANGED="true"

rollback

grep -Fq 'docker stop --time 610 worker-container' "$COMMAND_LOG"
grep -Fq "git reset --hard $PREVIOUS_SHA" "$COMMAND_LOG"
grep -Fq 'docker compose build api worker' "$COMMAND_LOG"
grep -Fq 'docker compose up -d --no-deps api' "$COMMAND_LOG"
grep -Fq 'docker compose up -d --no-deps --force-recreate caddy' "$COMMAND_LOG"
grep -Fq 'docker compose up -d --no-deps worker' "$COMMAND_LOG"
grep -Fq 'verify_public_health' "$COMMAND_LOG"
[[ "$DEPLOYED_SHA" == "$PREVIOUS_SHA" ]]

MUTATION_STARTED="true"
DEPLOY_RESULT="failed"
ROLLBACK_OCCURRED="false"

rollback() {
    DEPLOYED_SHA="$PREVIOUS_SHA"
    return 0
}

if (on_error 42 99) > "$REPORT_LOG" 2>&1; then
    printf 'on_error unexpectedly succeeded\n' >&2
    exit 1
else
    error_status=$?
fi

[[ "$error_status" == "42" ]]
grep -Fq '::UNLXCK_REPORT::result=rolled_back' "$REPORT_LOG"
grep -Fq '::UNLXCK_REPORT::rollback=true' "$REPORT_LOG"

printf 'Hetzner deploy rollback tests passed\n'
