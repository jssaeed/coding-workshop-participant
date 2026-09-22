"""
Read-only view of the incidents table for the messages service.

A message is only as private as its ticket, so posting and reading both start
by checking who the ticket belongs to. Ticket management itself lives in the
incidents service.
"""

from lib.database import fetch_one

def find_access_row(incident_id):
    """Return the columns needed to decide who may read or post, or None."""
    return fetch_one(
        "SELECT id, reported_by, assigned_to, status FROM incidents WHERE id = %s",
        (incident_id,),
    )
