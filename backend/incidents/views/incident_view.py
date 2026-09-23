"""
Incident view: turns a joined ticket row into the JSON the frontend expects.

The flat row (reporter_name, assignee_email, building, ...) becomes nested
objects: reportedBy, assignedTo and location.
"""

from lib.labels import room_label


def serialize(row):
    if row["location_id"] is None:
        location = None
    else:
        location = {
            "id": row["location_id"],
            "building": {"id": row["building_id"], "name": row["building_name"]},
            "floor": row["floor"],
            "room": row["room"],  # the plain room index; null when no room was given
            # how the room is written: "12", or "512" when the building numbers by floor
            "roomLabel": room_label(row["floor"], row["room"], row["room_numbers_include_floor"], row["max_rooms"]),
        }

    # A null reporter means that account has since been deleted.
    if row["reported_by"] is None:
        reported_by = None
    else:
        reported_by = {
            "id": row["reported_by"],
            "name": row["reporter_name"],
            "email": row["reporter_email"],
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
        "reportedBy": reported_by,
        "assignedTo": assigned_to,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "resolvedAt": row["resolved_at"],
    }


def serialize_many(rows):
    return [serialize(row) for row in rows]

