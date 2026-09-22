"""
A read-only look at the incidents table, for checking who may use a thread.

Tickets themselves are managed by the incidents service.
"""

from lib.database import fetch_one


def find_basic(incident_id):
    return fetch_one(
        "SELECT id, status, reported_by, assigned_to FROM incidents WHERE id = %s",
        (incident_id,),
    )
