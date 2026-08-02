#!/usr/bin/env bash
set -Eeuo pipefail

# Generate and persist one VAPID key pair when both production values are empty.
# Existing keys are never rotated: changing the pair invalidates every browser
# subscription created with the previous public key.

env_file="${1:-/opt/unlxck/.env.production}"
umask 077

if [[ ! -f "$env_file" ]]; then
  echo "ERROR: environment file not found: $env_file" >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl is required to generate VAPID keys." >&2
  exit 1
fi

read_env_value() {
  local key="$1"
  awk -v wanted="$key" '
    index($0, wanted "=") == 1 {
      value = substr($0, length(wanted) + 2)
      sub(/\r$/, "", value)
    }
    END { print value }
  ' "$env_file"
}

private_key="$(read_env_value UNLXCK_VAPID_PRIVATE_KEY)"
public_key="$(read_env_value UNLXCK_VAPID_PUBLIC_KEY)"

if [[ -n "$private_key" && -n "$public_key" ]]; then
  echo "already-configured"
  exit 0
fi
if [[ -n "$private_key" || -n "$public_key" ]]; then
  echo "ERROR: partial VAPID configuration found; refusing to rotate or replace one key." >&2
  exit 1
fi

pem_file="$(mktemp)"
env_dir="$(dirname "$env_file")"
tmp_env="$(mktemp "$env_dir/.vapid-env.XXXXXX")"
cleanup() {
  rm -f "$pem_file" "$tmp_env"
}
trap cleanup EXIT

openssl ecparam -genkey -name prime256v1 -out "$pem_file" >/dev/null 2>&1
public_key="$(
  openssl ec -in "$pem_file" -pubout -outform DER 2>/dev/null \
    | tail -c 65 \
    | base64 \
    | tr -d '\n=' \
    | tr '/+' '_-'
)"
private_key="$(
  openssl ec -in "$pem_file" -outform DER 2>/dev/null \
    | tail -c +8 \
    | head -c 32 \
    | base64 \
    | tr -d '\n=' \
    | tr '/+' '_-'
)"

# A P-256 uncompressed public point is 65 bytes (87 base64url characters);
# the private scalar is 32 bytes (43 base64url characters).
if [[ ${#public_key} -ne 87 || ${#private_key} -ne 43 ]]; then
  echo "ERROR: generated VAPID key lengths were invalid." >&2
  exit 1
fi

# Remove blank/duplicate key declarations and then append one matching pair.
awk '
  $0 !~ /^UNLXCK_VAPID_PRIVATE_KEY=/ &&
  $0 !~ /^UNLXCK_VAPID_PUBLIC_KEY=/
' "$env_file" > "$tmp_env"
printf '\n# Browser Web Push credentials; generated once on the production server.\n' >> "$tmp_env"
printf 'UNLXCK_VAPID_PRIVATE_KEY=%s\n' "$private_key" >> "$tmp_env"
printf 'UNLXCK_VAPID_PUBLIC_KEY=%s\n' "$public_key" >> "$tmp_env"

chmod --reference="$env_file" "$tmp_env"
mv -f "$tmp_env" "$env_file"
trap - EXIT
rm -f "$pem_file"

echo "generated"
