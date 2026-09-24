#!/usr/bin/env bash
# Script: Load Test
# Purpose: Run the Artillery load test (backend/_load/artillery.yml) against a server
# Usage: ./bin/load-test.sh <base_url> [--profile smoke|full|heavy] [--email x --password y]
#
# Needs Node (npx fetches Artillery on first use). Unless --email is given, a
# throw-away employee account (loadtest-<time>@acme.inc) is signed up first
# and the test runs as that user; the tickets it files stay in the database.
#
# Run this against the CLOUD deployment. Locally every Lambda is one Docker
# container with no scaling, so local numbers say nothing about production.
#   ./bin/load-test.sh "$(cd infra && terraform output -raw api_base_url)" --profile smoke
#
# Profiles (see artillery.yml):  smoke  20 s at 2 new users/s, to check the setup
#                                full   ramp to 15 new users/s, hold 90 s (default)
#                                heavy  ramp to 40 new users/s, hold 120 s
# The run fails when p95 > 1.5 s, p99 > 3 s, or more than 1% of requests error.
# The JSON report lands in test-results/load/.

set -u

if [ $# -eq 0 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" > /dev/null 2>&1 || exit 1; pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." > /dev/null 2>&1 || exit 1; pwd -P)"
LOAD_DIR="$PROJECT_ROOT/backend/_load"
REPORT_DIR="$PROJECT_ROOT/test-results/load"

BASE_URL="${1%/}"; shift
PROFILE="full"
EMAIL="${LOAD_EMAIL:-}"
PASSWORD="${LOAD_PASSWORD:-}"
while [ $# -gt 0 ]; do
    case "$1" in
        --profile) PROFILE="$2"; shift ;;
        --email) EMAIL="$2"; shift ;;
        --password) PASSWORD="$2"; shift ;;
        *) echo "ERROR: unknown option $1"; exit 1 ;;
    esac
    shift
done

command -v npx > /dev/null 2>&1 || { echo "ERROR: 'npx' (Node.js) is missing. Aborting..."; exit 1; }
command -v python3 > /dev/null 2>&1 || { echo "ERROR: 'python3' is missing. Aborting..."; exit 1; }

echo "==============================="
echo "Coding Workshop - Load Test"
echo "==============================="
echo "Target:  $BASE_URL"
echo "Profile: $PROFILE"

# Is the server there?
if ! curl -sf --max-time 10 "$BASE_URL/api/users/branches" > /dev/null; then
    echo "ERROR: $BASE_URL/api/users/branches does not answer"
    exit 1
fi
case "$BASE_URL" in
    *localhost*|*127.0.0.1*) echo "WARN: local Lambdas do not scale; these numbers are not representative of the cloud" ;;
esac

# Sign up a throw-away account unless one was given.
if [ -z "$EMAIL" ]; then
    EMAIL="loadtest-$(date +%s)@acme.inc"
    PASSWORD="loadtest-pw-$(date +%s)"
    BRANCH_ID="$(curl -sf --max-time 10 "$BASE_URL/api/users/branches" | python3 -c 'import sys, json; print(json.load(sys.stdin)[0]["id"])')"
    STATUS="$(curl -s --max-time 20 -o /dev/null -w '%{http_code}' -X POST "$BASE_URL/api/users" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"name\":\"Load Test\",\"branchId\":$BRANCH_ID}")"
    if [ "$STATUS" != "201" ]; then
        echo "ERROR: could not create the load-test account (HTTP $STATUS)"
        exit 1
    fi
    echo "Account: $EMAIL (created for this run)"
else
    echo "Account: $EMAIL"
fi
echo ""

mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/$(date +%Y%m%d-%H%M%S)-$PROFILE.json"

ARGS=(run "$LOAD_DIR/artillery.yml" --target "$BASE_URL" --output "$REPORT"
      --variables "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
ARGS+=(--environment "$PROFILE")

npx --yes artillery@2 "${ARGS[@]}"
RESULT=$?

echo ""
echo "Report: $REPORT"
exit $RESULT
