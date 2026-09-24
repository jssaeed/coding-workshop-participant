"""Test setup for the incidents service. See backend/TESTING.md."""

import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_DIR = os.path.dirname(TESTS_DIR)
BACKEND_DIR = os.path.dirname(SERVICE_DIR)

# backend/ for the shared test helpers, the service folder for its packages
# (function, controllers, models, views, lib) and vendored dependencies.
for path in (BACKEND_DIR, SERVICE_DIR):
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)

from _testing import db as testdb  # noqa: E402

testdb.configure_environment()  # before anything imports lib.database

from _testing.fixtures import *  # noqa: E402,F401,F403
