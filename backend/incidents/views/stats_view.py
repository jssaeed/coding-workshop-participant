"""
Stats view: turns count rows into the JSON the Statistics page expects.
"""

from models.incident import CATEGORIES, MAX_PRIORITY, MIN_PRIORITY, STATUSES


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


def priority_counts(rows):
    """
    {"1": 4, "2": 7, "3": 20, "4": 6, "5": 5}

    Every priority from 1 (most urgent) to 5 is present, with 0 when empty,
    so the chart always has the same slices in the same order. The keys are
    strings because that is what JSON objects have.
    """
    counts = {str(priority): 0 for priority in range(MIN_PRIORITY, MAX_PRIORITY + 1)}
    for row in rows:
        counts[str(row["priority"])] = row["count"]
    return counts


def category_counts(rows):
    """
    {"plumbing": 6, "electrical": 3, ..., "other": 1}

    Every category is present, in the order of CATEGORIES, with 0 when
    empty, so the chart always has the same bars and a category with no
    tickets still shows as a zero.
    """
    counts = {category: 0 for category in CATEGORIES}
    for row in rows:
        counts[row["category"]] = row["count"]
    return counts


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


def seconds(value):
    """AVG() comes back as a Decimal; the API sends a plain number (or null)."""
    return None if value is None else float(value)


def resolution(row):
    """{"averageSeconds": 93600.0, "resolvedCount": 12}"""
    return {"averageSeconds": seconds(row["average_seconds"]), "resolvedCount": row["resolved_count"]}


def engineers(rows):
    """[{"id": 7, "name": "Hugh", "role": "engineer", "assigned": 13, "resolved": 4, "averageSeconds": 3600.0}]"""
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "role": row["role"],
            "assigned": row["assigned_count"],
            "resolved": row["resolved_count"],
            "averageSeconds": seconds(row["average_seconds"]),
        }
        for row in rows
    ]
