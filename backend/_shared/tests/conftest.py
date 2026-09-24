"""
Test setup for backend/_shared.

The shared files use relative imports (from .database import ...) and are
deployed as each service's lib/ package. Here they are made importable under
that same name, "lib", straight from backend/_shared, so these tests check
the source of truth rather than one of its copies.
"""

import os
import sys
import types

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.dirname(TESTS_DIR)
BACKEND_DIR = os.path.dirname(SHARED_DIR)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if "lib" not in sys.modules:
    lib = types.ModuleType("lib")
    lib.__path__ = [SHARED_DIR]
    sys.modules["lib"] = lib

# Unit tests only: no database, and a fixed signing secret.
os.environ.setdefault("PSYCOPG_IMPL", "python")
os.environ.setdefault("IS_LOCAL", "true")
os.environ.setdefault("JWT_SECRET", "test-signing-secret-long-enough-for-hmac-sha256")

from _testing.fixtures import no_database  # noqa: E402,F401
