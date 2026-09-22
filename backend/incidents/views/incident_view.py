"""
Incident view: turns joined incident rows into JSON for the frontend.

Nests the reporter, assignee and location so a ticket arrives as one object
rather than a flat row of foreign keys.
"""

def _person(user_id, name, email):
    """Render a joined user, or None when there is no row (unassigned)."""
    if user_id is None:
        return None
    return {"id": user_id, "name": name, "email": email}

def _location(row):
    """Render the joined location, or None when the ticket has no place set."""
    if row.get("location_id") is None:
        return None
    return {
        "id": row["location_id"],
        "building": row["building"],
        "floor": row["floor"],
        # Stored as an empty string so the uniqueness constraint works; the API
        # reports "no room given" as null.
        "room": row["room"] or None,
    }

def serialize(row):
    """Render one incident row."""
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "location": _location(row),
        "reportedBy": _person(
            row["reported_by"], row["reporter_name"], row["reporter_email"]
        ),
        "assignedTo": _person(
            row["assigned_to"], row.get("assignee_name"), row.get("assignee_email")
        ),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "resolvedAt": row["resolved_at"],
    }

def serialize_many(rows):
    """Render a list of incident rows."""
    return [serialize(row) for row in rows]

def serialize_location(row):
    """Render a standalone location row."""
    return {
        "id": row["id"],
        "building": row["building"],
        "floor": row["floor"],
        "room": row["room"] or None,
    }
