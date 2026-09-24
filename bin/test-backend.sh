#!/usr/bin/env bash
# Script: Backend Tests
# Purpose: Run the pytest suite of every backend service (and backend/_shared)
# Usage: ./bin/test-backend.sh [--cov] [--unit] [service ...] [-- pytest args]
#
# Each service is its own Lambda with its own top-level packages (controllers,
# models, views, lib), so the suites cannot share one pytest process: this
# script runs pytest once per service, from that service's folder.
#
# Integration tests need PostgreSQL (the same one bin/start-dev.sh starts).
# They use a separate database, incident_tracker_test, and skip themselves
# when the server is not reachable. See backend/TESTING.md.
#
# Results are written to test-results/backend/: one JUnit XML file per
# service (<service>.xml), coverage XML with --cov (coverage-<service>.xml),
# and summary.txt with the outcome of every service and the time of the run.

set -u

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    echo "Usage: $0 [--cov] [--unit] [service ...] [-- pytest args]"
    echo ""
    echo "Options:"
    echo "  --cov        Report line and branch coverage per service"
    echo "  --unit       Skip the integration tests (no database needed)"
    echo "  service      Only run these services (default: _shared and every service)"
    echo "  -- args      Passed to pytest, e.g. -- -k login -x"
    exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" > /dev/null 2>&1 || exit 1; pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." > /dev/null 2>&1 || exit 1; pwd -P)"
BACKEND_DIR="$PROJECT_ROOT/backend"
RESULTS_DIR="$PROJECT_ROOT/test-results/backend"
mkdir -p "$RESULTS_DIR"

# Use the backend virtualenv when it exists, otherwise whatever python is first.
PYTHON="$BACKEND_DIR/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="$(command -v python3 || command -v python)"

COVERAGE=0
PYTEST_ARGS=()
SERVICES=()
while [ $# -gt 0 ]; do
    case "$1" in
        --cov) COVERAGE=1 ;;
        --unit) PYTEST_ARGS+=(-m "not integration") ;;
        --) shift; PYTEST_ARGS+=("$@"); break ;;
        *) SERVICES+=("$1") ;;
    esac
    shift
done

if [ ${#SERVICES[@]} -eq 0 ]; then
    SERVICES=(_shared)
    for dir in "$BACKEND_DIR"/*/; do
        name="$(basename "$dir")"
        [[ "$name" == _* || "$name" == .* ]] && continue
        [ -d "$dir/tests" ] || continue
        SERVICES+=("$name")
    done
fi

if ! "$PYTHON" -c "import pytest" > /dev/null 2>&1; then
    echo "ERROR: pytest is missing. Install it with:"
    echo "  $PYTHON -m pip install -r $BACKEND_DIR/requirements-dev.txt"
    exit 1
fi

FAILED=()
SUMMARY="$RESULTS_DIR/summary.txt"
{
    echo "Backend test run: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Python: $("$PYTHON" --version 2>&1)   Coverage: $COVERAGE   Pytest args: ${PYTEST_ARGS[*]:-none}"
    echo ""
} > "$SUMMARY"
for service in "${SERVICES[@]}"; do
    dir="$BACKEND_DIR/$service"
    if [ ! -d "$dir/tests" ]; then
        echo "WARN: $service has no tests folder, skipping"
        continue
    fi
    echo ""
    echo "=== $service ==="
    args=(tests "${PYTEST_ARGS[@]}" --junitxml="$RESULTS_DIR/$service.xml" -o junit_suite_name="$service")
    if [ $COVERAGE -eq 1 ]; then
        args+=(--cov-config="$BACKEND_DIR/.coveragerc" --cov-report=term --cov-report="xml:$RESULTS_DIR/coverage-$service.xml")
        # The shared library is measured once, by its own suite; a service's
        # lib/ copy would only dilute the service's number with code it never calls.
        if [ "$service" = "_shared" ]; then
            args+=(--cov=lib)
        else
            args+=(--cov=function --cov=controllers --cov=models --cov=views)
        fi
    fi
    # Coverage data goes under backend/ (gitignored as .coverage.*), not into the service folder.
    if (cd "$dir" && COVERAGE_FILE="$BACKEND_DIR/.coverage.$service" "$PYTHON" -m pytest "${args[@]}"); then
        outcome="passed"
    else
        outcome="FAILED"
        FAILED+=("$service")
    fi
    # One line per service: outcome and the counts from the JUnit file
    counts="$("$PYTHON" - "$RESULTS_DIR/$service.xml" <<'PY'
import sys, xml.etree.ElementTree as ET
suite = ET.parse(sys.argv[1]).getroot().find("testsuite")
a = suite.attrib
print(f"tests={a['tests']} failures={a['failures']} errors={a['errors']} skipped={a['skipped']} time={float(a['time']):.1f}s")
PY
    )"
    printf '%-12s %-7s %s\n' "$service" "$outcome" "$counts" >> "$SUMMARY"
done

echo ""
echo "Results: $RESULTS_DIR"
cat "$SUMMARY"
if [ ${#FAILED[@]} -gt 0 ]; then
    echo "FAILED: ${FAILED[*]}"
    exit 1
fi
echo "All backend test suites passed."
