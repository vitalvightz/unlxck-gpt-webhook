#!/usr/bin/env bash

set -Eeuo pipefail

TARGET_SHA="${1:-}"
DEPLOY_ROOT="${2:-/opt/unlxck}"
HEALTH_URL="${3:-}"

PREVIOUS_SHA="unknown"
DEPLOYED_SHA="unknown"
DEPLOY_RESULT="failed"
API_HEALTH_RESULT="not_checked"
API_CONTAINER_STATUS="unknown"
WORKER_CONTAINER_STATUS="unknown"
ROLLBACK_OCCURRED="false"
MUTATION_STARTED="false"
CADDY_CHANGED="false"

report() {
    printf '%s\n' \
        "::UNLXCK_REPORT::target_sha=${TARGET_SHA:-unknown}" \
        "::UNLXCK_REPORT::previous_sha=${PREVIOUS_SHA}" \
        "::UNLXCK_REPORT::deployed_sha=${DEPLOYED_SHA}" \
        "::UNLXCK_REPORT::result=${DEPLOY_RESULT}" \
        "::UNLXCK_REPORT::api_health=${API_HEALTH_RESULT}" \
        "::UNLXCK_REPORT::api_status=${API_CONTAINER_STATUS}" \
        "::UNLXCK_REPORT::worker_status=${WORKER_CONTAINER_STATUS}" \
        "::UNLXCK_REPORT::rollback=${ROLLBACK_OCCURRED}"
}

die() {
    printf 'Deployment error: %s\n' "$*" >&2
    return 1
}

container_state() {
    local service="$1"
    local container_id

    container_id="$(docker compose ps -q "$service" 2>/dev/null || true)"
    if [[ -z "$container_id" ]]; then
        printf 'missing'
        return 0
    fi

    docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || printf 'unknown'
}

wait_for_api_health() {
    local timeout_seconds="${1:-180}"
    local deadline=$((SECONDS + timeout_seconds))
    local container_id
    local health_status

    container_id="$(docker compose ps -q api)"
    [[ -n "$container_id" ]] || die "api container was not created"

    while ((SECONDS < deadline)); do
        health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
        case "$health_status" in
            healthy)
                API_HEALTH_RESULT="container_healthy"
                return 0
                ;;
            unhealthy | exited | dead)
                die "api container entered ${health_status} state"
                ;;
        esac
        sleep 5
    done

    die "api container did not become healthy within ${timeout_seconds} seconds"
}

verify_public_health() {
    local response_code

    response_code="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
        --connect-timeout 10 --max-time 30 "$HEALTH_URL")"
    [[ "$response_code" == "200" ]] || die "public health endpoint returned HTTP ${response_code}"
    API_HEALTH_RESULT="http_200"
}

verify_worker() {
    local container_id
    local running

    container_id="$(docker compose ps -q worker)"
    [[ -n "$container_id" ]] || die "worker container was not created"

    sleep 10
    running="$(docker inspect --format '{{.State.Running}}' "$container_id")"
    [[ "$running" == "true" ]] || die "worker container is not running"

    docker compose logs --no-color --tail=100 worker \
        | grep -Fq '[worker] started mode=' \
        || die "worker startup signal was not found in recent logs"
}

inspect_startup_logs() {
    local api_logs

    api_logs="$(docker compose logs --no-color --tail=100 api 2>&1)"

    if grep -Eqi 'Traceback|Application startup failed|startup_failure' <<<"$api_logs"; then
        die "api logs contain an obvious startup failure"
    fi
    grep -Fq 'Application startup complete.' <<<"$api_logs" \
        || die "api startup completion signal was not found in recent logs"
}

stop_running_worker() {
    local container_id

    container_id="$(docker ps -q \
        --filter 'label=com.docker.compose.project=unlxck-backend' \
        --filter 'label=com.docker.compose.service=worker' \
        | head -1)"
    if [[ -n "$container_id" ]]; then
        docker stop --time 610 "$container_id" >/dev/null
    fi
}

rollback() {
    [[ "$PREVIOUS_SHA" != "unknown" ]] || return 1

    cd "$DEPLOY_ROOT"
    # Stop independently of the checked-out Compose file so rollback still
    # works when target configuration validation itself caused the failure.
    stop_running_worker
    git reset --hard "$PREVIOUS_SHA"
    docker compose config --quiet
    docker compose build api worker
    docker compose up -d --no-deps api
    wait_for_api_health 180

    if [[ "$CADDY_CHANGED" == "true" ]]; then
        docker compose up -d --no-deps --force-recreate caddy
    fi

    docker compose up -d --no-deps worker
    verify_worker
    verify_public_health

    DEPLOYED_SHA="$PREVIOUS_SHA"
    API_CONTAINER_STATUS="$(container_state api)"
    WORKER_CONTAINER_STATUS="$(container_state worker)"
}

on_error() {
    local exit_code="$1"
    local line_number="$2"

    trap - ERR
    set +e
    printf 'Deployment failed at line %s; attempting rollback.\n' "$line_number" >&2

    if [[ "$MUTATION_STARTED" == "true" ]] && rollback; then
        ROLLBACK_OCCURRED="true"
        DEPLOY_RESULT="rolled_back"
    elif [[ "$MUTATION_STARTED" == "true" ]]; then
        ROLLBACK_OCCURRED="failed"
        DEPLOY_RESULT="rollback_failed"
    fi

    API_CONTAINER_STATUS="$(container_state api)"
    WORKER_CONTAINER_STATUS="$(container_state worker)"
    report
    exit "$exit_code"
}

main() {
    local branch_name
    local lock_file

    [[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || die "target SHA must be a full 40-character Git commit"
    [[ "$HEALTH_URL" == https://*/health ]] || die "health URL must be an HTTPS /health endpoint"

    for required_command in git docker curl flock grep; do
        command -v "$required_command" >/dev/null || die "required command is missing: ${required_command}"
    done

    lock_file="${HOME}/.unlxck-deploy.lock"
    exec 9>"$lock_file"
    flock -n 9 || die "another deployment is already running"

    cd "$DEPLOY_ROOT"
    [[ -d .git ]] || die "deployment path is not a Git checkout: ${DEPLOY_ROOT}"
    [[ -f .env.production && ! -L .env.production ]] || die ".env.production must be a regular file"
    if git ls-files --error-unmatch .env.production >/dev/null 2>&1; then
        die ".env.production must never be tracked by Git"
    fi

    branch_name="$(git branch --show-current)"
    [[ "$branch_name" == "Main" ]] || die "server checkout must be on Main, found ${branch_name:-detached}"

    PREVIOUS_SHA="$(git rev-parse HEAD)"
    DEPLOYED_SHA="$PREVIOUS_SHA"

    git fetch --prune origin Main
    git cat-file -e "${TARGET_SHA}^{commit}"
    git merge-base --is-ancestor "$TARGET_SHA" origin/Main \
        || die "target SHA is not reachable from origin/Main"

    if ! git diff --quiet "$PREVIOUS_SHA" "$TARGET_SHA" -- Caddyfile compose.yaml; then
        CADDY_CHANGED="true"
    fi

    MUTATION_STARTED="true"
    git reset --hard "$TARGET_SHA"
    [[ "$(git rev-parse HEAD)" == "$TARGET_SHA" ]] || die "checkout did not reach the requested target SHA"
    git check-ignore -q .env.production || die ".env.production is not protected by .gitignore"

    docker compose config --quiet
    docker compose build api worker

    docker compose up -d --no-deps api
    wait_for_api_health 180

    if [[ "$CADDY_CHANGED" == "true" ]]; then
        docker compose up -d --no-deps --force-recreate caddy
    fi

    verify_public_health

    # Compose stops the existing worker before starting its replacement. The
    # service's 10-minute shutdown grace lets an in-flight plan finish without
    # ever running two queue consumers simultaneously.
    docker compose up -d --no-deps worker
    verify_worker
    inspect_startup_logs
    verify_public_health

    API_CONTAINER_STATUS="$(container_state api)"
    WORKER_CONTAINER_STATUS="$(container_state worker)"
    [[ "$API_CONTAINER_STATUS" == "running" ]] || die "api container is not running after deployment"
    [[ "$WORKER_CONTAINER_STATUS" == "running" ]] || die "worker container is not running after deployment"

    docker compose ps
    docker image prune --force >/dev/null

    DEPLOYED_SHA="$TARGET_SHA"
    DEPLOY_RESULT="success"
    report
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    trap 'on_error $? $LINENO' ERR
    main
fi
