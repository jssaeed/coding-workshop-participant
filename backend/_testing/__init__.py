"""
Helpers shared by every backend test suite.

Each service's tests/conftest.py puts backend/ on sys.path and imports from
here, so the event builders, fake database and integration fixtures are
written once instead of once per service.
"""
