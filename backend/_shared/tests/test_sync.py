"""
Every service's lib/ folder must be an exact copy of backend/_shared.

The copies are what deploys (each Lambda is built from its own folder), so
an edit to _shared that was not followed by bin/sync-shared.sh would ship
stale code. This test fails until the script is run.
"""

import os

import pytest

from conftest import BACKEND_DIR, SHARED_DIR

SHARED_FILES = sorted(name for name in os.listdir(SHARED_DIR) if name.endswith(".py"))
SERVICES = sorted(
    name for name in os.listdir(BACKEND_DIR)
    if not name.startswith(("_", "."))
    and os.path.isfile(os.path.join(BACKEND_DIR, name, "requirements.txt"))
)


def test_there_are_python_services():
    assert SERVICES, "no Python services found under backend/"


@pytest.mark.parametrize("service", SERVICES)
def test_lib_is_a_package(service):
    assert os.path.isfile(os.path.join(BACKEND_DIR, service, "lib", "__init__.py"))


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize("file_name", SHARED_FILES)
def test_lib_copy_matches_shared_source(service, file_name):
    with open(os.path.join(SHARED_DIR, file_name), encoding="utf-8") as source:
        expected = f"# Copied from backend/_shared/{file_name} by bin/sync-shared.sh - do not edit.\n" + source.read()
    copy_path = os.path.join(BACKEND_DIR, service, "lib", file_name)
    assert os.path.isfile(copy_path), f"{service}/lib/{file_name} is missing: run bin/sync-shared.sh"
    with open(copy_path, encoding="utf-8") as copy:
        assert copy.read() == expected, f"{service}/lib/{file_name} is stale: run bin/sync-shared.sh"
