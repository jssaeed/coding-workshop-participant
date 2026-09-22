#!/usr/bin/env bash
# Copies backend/_shared/*.py into the lib/ folder of every backend service.
#
# Why: each service is deployed as its own Lambda, built from its own folder,
# so a service can only import files that are inside its folder. Code that
# every service needs (database, auth, ...) is kept once in backend/_shared
# and copied into each service by this script.
#
# Edit the files in backend/_shared, then run:  ./bin/sync-shared.sh
# Never edit the copies in a service's lib/ folder; they get overwritten.

set -e

# Find the project folder (one level up from this script)
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHARED_DIR="$PROJECT_ROOT/backend/_shared"

for service_dir in "$PROJECT_ROOT"/backend/*/; do
    service_name="$(basename "$service_dir")"

    # Skip folders that are not services (_examples, _shared, .venv, ...)
    if [[ "$service_name" == _* || "$service_name" == .* ]]; then
        continue
    fi
    # Only Python services use the shared code
    if [[ ! -f "$service_dir/requirements.txt" ]]; then
        continue
    fi

    mkdir -p "$service_dir/lib"

    # Copy each shared file, with a note at the top saying not to edit it
    for shared_file in "$SHARED_DIR"/*.py; do
        file_name="$(basename "$shared_file")"
        {
            echo "# Copied from backend/_shared/$file_name by bin/sync-shared.sh - do not edit."
            cat "$shared_file"
        } > "$service_dir/lib/$file_name"
    done

    # An __init__.py file makes lib/ importable as a Python package
    echo '"""Shared code copied from backend/_shared. Do not edit."""' > "$service_dir/lib/__init__.py"

    echo "  synced backend/$service_name/lib"
done
