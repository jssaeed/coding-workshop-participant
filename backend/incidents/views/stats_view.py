"""
Stats view: turns count rows into the JSON the Statistics page expects.
"""

from models.incident import STATUSES


def status_counts(rows):
    """
    {"total": 12, "byStatus": {"open": 5, "in_progress": 3, ...}}

    Every status is present, with 0 when there were no tickets in it, so
    the chart always has the same segments in the same order.
    """
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] = row["count"]
    return {"total": sum(counts.values()), "byStatus": counts}


def building_counts(rows):
    """[{"id": 1, "name": "HQ", "count": 7}, {"id": null, "name": "No location", "count": 2}]"""
    return [
        {
            "id": row["building_id"],
            "name": row["building_name"] if row["building_id"] is not None else "No location",
            "count": row["count"],
        }
        for row in rows
    ]


def floor_counts(rows):
    """[{"floor": 1, "count": 3}, ...]"""
    return [{"floor": row["floor"], "count": row["count"]} for row in rows]


def room_counts(rows, label_for):
    """
    [{"room": 12, "label": "512", "count": 3}, {"room": null, "label": null, "count": 1}]
    (null = no room given). label_for(room) writes the room the building's way.
    """
    return [{"room": row["room"], "label": label_for(row["room"]), "count": row["count"]} for row in rows]
