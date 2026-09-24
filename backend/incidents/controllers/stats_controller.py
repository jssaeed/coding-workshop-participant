"""
Stats controller: numbers for the Statistics page.

- Admins see everything: totals by status, and a drill-down of tickets per
  building, then per floor, then per room.
- Everyone sees their own numbers: tickets they reported by status, and, for
  engineers and admins, tickets assigned to them by status.

All endpoints take ?days=N (default 30, at most 365): only tickets created in
the last N days are counted.
"""

from datetime import datetime, timedelta, timezone

from lib import auth
from lib.labels import room_label
from lib.request import query_params
from lib.responses import HttpError, ok
from models import building as building_model
from models import stats as stats_model
from views import stats_view

DEFAULT_DAYS = 30
MAX_DAYS = 365


def since_from_query(params):
    """Turn ?days=N into the earliest created_at to count from."""
    days = params.get("days", str(DEFAULT_DAYS))
    if not days.isdigit() or not 1 <= int(days) <= MAX_DAYS:
        raise HttpError(400, f"'days' must be between 1 and {MAX_DAYS}")
    return datetime.now(timezone.utc) - timedelta(days=int(days))


def positive_int_param(params, name):
    """Read an optional ?name=N (a positive whole number), or None."""
    value = params.get(name)
    if value is None:
        return None
    if not value.isdigit() or int(value) < 1:
        raise HttpError(400, f"'{name}' must be a positive whole number")
    return int(value)


def overview(event):
    """
    GET /api/incidents/stats/overview?days=30 - all tickets by status, plus
    how long tickets took to resolve. Admin only.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    since = since_from_query(query_params(event))
    result = stats_view.status_counts(stats_model.count_by_status(since))
    result["resolution"] = stats_view.resolution(stats_model.resolution_time(since))
    return ok(result)


def engineers(event):
    """
    GET /api/incidents/stats/engineers?days=30 - per engineer: tickets
    assigned, tickets resolved and average resolution time. Admin only.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    since = since_from_query(query_params(event))
    return ok(stats_view.engineers(stats_model.engineer_workload(since)))


def locations(event):
    """
    GET /api/incidents/stats/locations?days=30            tickets per building
    GET ...?buildingId=2                                  tickets per floor in that building
    GET ...?buildingId=2&floor=3                          tickets per room on that floor
    Admin only.
    """
    caller = auth.current_user(event)
    auth.require_role(caller, [auth.ROLE_ADMIN])

    params = query_params(event)
    since = since_from_query(params)
    building_id = positive_int_param(params, "buildingId")
    floor = positive_int_param(params, "floor")

    if building_id is None:
        return ok({"level": "building", "items": stats_view.building_counts(stats_model.count_by_building(since))})

    building = building_model.find_by_id(building_id)
    if building is None:
        raise HttpError(404, "Building not found")

    if floor is None:
        return ok({
            "level": "floor",
            "building": {"id": building["id"], "name": building["name"]},
            "items": stats_view.floor_counts(stats_model.count_by_floor(building_id, since)),
        })

    rows = stats_model.count_by_room(building_id, floor, since)
    return ok({
        "level": "room",
        "building": {"id": building["id"], "name": building["name"]},
        "floor": floor,
        "items": stats_view.room_counts(
            rows, lambda room: room_label(floor, room, building["room_numbers_include_floor"], building["max_rooms"])
        ),
    })


def mine(event):
    """
    GET /api/incidents/stats/mine?days=30 - the caller's own numbers.

    "reported": tickets I filed, by status. "assigned": tickets assigned to
    me, by status (only for engineers and admins; null for employees).
    """
    caller = auth.current_user(event)
    since = since_from_query(query_params(event))

    reported = stats_view.status_counts(stats_model.count_by_status(since, reported_by=caller["id"]))

    assigned = None
    if auth.is_staff(caller):
        assigned = stats_view.status_counts(stats_model.count_by_status(since, assigned_to=caller["id"]))

    return ok({"reported": reported, "assigned": assigned})
