# Copied from backend/_shared/labels.py by bin/sync-shared.sh - do not edit.
"""
How floors and rooms are written for people.

Floors: 1..n above ground, -1..-m below; -1 is "B1".

Rooms are stored as a plain index (1, 2, 3 ...) on their floor. A building
can choose to number rooms with the floor in front: room 1 on floor 5 is
"501" when every floor has fewer than 100 rooms, or "5001" when any floor
has 100 or more (two or three digits for the room part). On a basement
floor the same rule gives "B101".
"""


def floor_label(floor):
    """-2 -> 'B2', 3 -> '3'."""
    return f"B{-floor}" if floor < 0 else str(floor)


def room_digits(max_rooms):
    """How many digits the room part needs: 2 below 100 rooms, else 3."""
    return 2 if (max_rooms or 0) < 100 else 3


def room_label(floor, room, include_floor, max_rooms):
    """'501' / 'B101' when the building numbers rooms by floor, else '1'."""
    if room is None:
        return None
    if not include_floor:
        return str(room)
    return f"{floor_label(floor)}{room:0{room_digits(max_rooms)}d}"
