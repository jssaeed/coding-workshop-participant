"""
A read-only look at the incidents table, for checking who may use a thread.

Tickets themselves are managed by the incidents service.
"""

from lib.database import fetch_one


def find_basic(incident_id, lock=False):
    """
    One ticket's id, status, reporter and assignee, or None.

    lock=True adds FOR SHARE: the ticket cannot be changed (for example
    closed) by someone else until the current transaction ends.
    """
    sql = "SELECT id, status, reported_by, assigned_to FROM incidents WHERE id = %s"
    if lock:
        sql += " FOR SHARE"
    return fetch_one(sql, (incident_id,))
