#!/usr/bin/env bash
# Script: Smoke Test
# Purpose: Run the HTTP smoke tests (backend/_e2e) against a running server
# Usage: ./bin/smoke-test.sh [base_url] [-- pytest args]
# Default: http://localhost:3001 (the local environment from bin/start-dev.sh)
#
# For the cloud deployment, pass the URL that bin/deploy-backend.sh printed:
#   ./bin/smoke-test.sh "$(cd infra && terraform output -raw api_base_url)"

set -u

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    echo "Usage: $0 [base_url] [-- pytest args]"
    echo "Run the HTTP smoke tests against a running server (default http://localhost:3001)."
    echo ""
    echo "Environment:"
    echo "  SMOKE_ADMIN_EMAIL / SMOKE_ADMIN_PASSWORD   db admin used to delete the test accounts afterwards"
    echo "                                             (default admin@admin.com / admin123, the migration's account)"
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" > /dev/null 2>&1 || exit 1; pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." > /dev/null 2>&1 || exit 1; pwd -P)"
BACKEND_DIR="$PROJECT_ROOT/backend"

PYTHON="$BACKEND_DIR/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || command -v python)"

BASE_URL="${API_BASE_URL:-http://localhost:3001}"
if [ $# -gt 0 ] && [ "$1" != "--" ]; then
    BASE_URL="$1"
    shift
fi
[ "${1:-}" = "--" ] && shift

if ! "$PYTHON" -c "import pytest, requests" > /dev/null 2>&1; then
    echo "ERROR: pytest or requests is missing. Install them with:"
    echo "  $PYTHON -m pip install -r $BACKEND_DIR/requirements-dev.txt"
    exit 1
fi

echo "================================"
echo "Coding Workshop - Smoke Test"
echo "================================"
echo "Target: $BASE_URL"
echo ""

RESULTS_DIR="$PROJECT_ROOT/test-results/smoke"
mkdir -p "$RESULTS_DIR"
REPORT="$RESULTS_DIR/$(date +%Y%m%d-%H%M%S).xml"
echo "Report: $REPORT"
cd "$BACKEND_DIR/_e2e" && API_BASE_URL="$BASE_URL" "$PYTHON" -m pytest . -v --junitxml="$REPORT" -o junit_suite_name="smoke $BASE_URL" "$@"
