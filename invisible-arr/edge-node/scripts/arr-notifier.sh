#!/usr/bin/env bash
set -euo pipefail

# Args from rdt-client external-program hook:
#   %L -> category (sonarr|radarr)
#   %F -> content path
#   %I -> info hash
# Optional 4th arg: job_id
# Optional 5th arg: acquisition_mode (download|stream)
CATEGORY="${1:-}"
CONTENT_PATH="${2:-}"
INFO_HASH="${3:-}"
JOB_ID="${4:-}"
ACQUISITION_MODE="${5:-}"

if [[ -z "$CATEGORY" || -z "$CONTENT_PATH" ]]; then
  echo "usage: arr-notifier.sh <category> <content_path> <info_hash> [job_id]" >&2
  exit 2
fi

AGENT_API_URL="${AGENT_API_URL:-http://agent-api:8880}"
WEBHOOK_URL="${AGENT_API_URL%/}/v1/webhooks/rdt-complete"
WEBHOOK_TOKEN="${RDT_WEBHOOK_TOKEN:-}"

JSON="$(cat <<EOF
{
  "category": "$CATEGORY",
  "content_path": "$CONTENT_PATH",
  "info_hash": "$INFO_HASH",
  "job_id": "$JOB_ID",
  "acquisition_mode": "$ACQUISITION_MODE"
}
EOF
)"

if [[ -n "$WEBHOOK_TOKEN" ]]; then
  curl -fsS -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -H "X-Webhook-Token: $WEBHOOK_TOKEN" \
    -d "$JSON" >/dev/null
else
  curl -fsS -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "$JSON" >/dev/null
fi

echo "rdt webhook sent: category=$CATEGORY path=$CONTENT_PATH"
