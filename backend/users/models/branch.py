"""
Branch model: the SQL for the branches table (the company sites).

Branches are created by the migrations service; this service only reads them.
"""

from lib.database import fetch_all, fetch_one


def list_all():
    """Every branch, alphabetical."""
    return fetch_all("SELECT id, name FROM branches ORDER BY name")


def find_by_id(branch_id):
    """One branch, or None."""
    return fetch_one("SELECT id, name FROM branches WHERE id = %s", (branch_id,))
