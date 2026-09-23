"""
Building view: turns a buildings row plus its floor rows into JSON.

"rooms" lists every floor in display order (top floor first, then B1, B2,
...) with how many rooms it has; 0 means not specified.
"""


def serialize(row, floors):
    return {
        "id": row["id"],
        "branchId": row["branch_id"],
        "name": row["name"],
        "floors": row["floors"],
        "basementFloors": row["basement_floors"],
        # True: room 1 on floor 5 is written "501" ("5001" once a floor has 100+ rooms)
        "roomNumbersIncludeFloor": row["room_numbers_include_floor"],
        "rooms": [{"floor": f["floor"], "rooms": f["rooms"]} for f in floors],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def serialize_many(rows, floors_by_building):
    return [serialize(row, floors_by_building[row["id"]]) for row in rows]
