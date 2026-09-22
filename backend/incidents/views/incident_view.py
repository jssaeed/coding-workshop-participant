"""
Incident view: turns a joined ticket row into the JSON the frontend expects.

The flat row (reporter_name, assignee_email, building, ...) becomes nested
objects: reportedBy, assignedTo and location.
"""


def serialize(row):
    if row["location_id"] is None:
        location = None
    else:
        location = {
            "id": row["location_id"],
            "building": row["building"],
            "floor": row["floor"],
            # Stored as '' when not given; the API says null instead.
            "room": row["room"] or None,
        }

    if row["assigned_to"] is None:
        assigned_to = None
    else:
        assigned_to = {
            "id": row["assigned_to"],
            "name": row["assignee_name"],
            "email": row["assignee_email"],
        }

    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "location": location,
        "reportedBy": {
            "id": row["reported_by"],
            "name": row["reporter_name"],
            "email": row["reporter_email"],
        },
        "assignedTo": assigned_to,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "resolvedAt": row["resolved_at"],
    }


def serialize_many(rows):
    return [serialize(row) for row in rows]


def serialize_location(row):
    return {
        "id": row["id"],
        "building": row["building"],
        "floor": row["floor"],
        "room": row["room"] or None,
    }
