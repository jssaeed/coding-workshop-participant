# Incident Tracker API

Six Lambda services behind `/api/`: `users`, `buildings`, `incidents`, `messages`, `inbox`, and `migrations`. All requests and responses are JSON.

| Environment | Base URL |
| --- | --- |
| Local (`./bin/start-dev.sh`) | `http://localhost:3001` |
| Cloud (`./bin/deploy-backend.sh`) | `https://{API_BASE_URL}` — printed by the deploy script |

## Setup

1. Start the environment: `./bin/start-dev.sh`
2. Create the tables: `curl -X POST http://localhost:3001/api/migrations`
3. Sign up your first user (see `POST /api/users`), then make them an admin directly in the database — signup only ever creates employees, and only an admin can promote. The change takes effect on their next request; no need to sign out:
   ```sh
   psql -h localhost -U postgres -c "UPDATE users SET role = 'facility_admin' WHERE email = 'you@acme.inc'"
   ```
   Every later admin is promoted through the API.

Shared code lives in `backend/_shared/` and is copied into each service's `lib/` by `./bin/sync-shared.sh`. Run that script after editing anything in `_shared/` and commit the resulting `lib/` files — they are what deploys.

## Authentication

Log in to get two tokens:

- an **access token** (a JWT, valid 15 minutes) — send it on every other request as `Authorization: Bearer <token>`
- a **refresh token** (valid 14 days) — send it only to `POST /api/users/refresh` to get a new pair when the access token expires. Each refresh token works exactly once; the response contains its replacement.

Expired and revoked refresh tokens are deleted automatically on every login, so the table stays small.

The access token carries the user's id and role, but the role is only a hint for the client. Every service verifies the token's signature to learn **who** is calling, then reads the user's **current** role from the database. A promotion or demotion therefore applies on the very next request, without a new login. Demoting a user also revokes their refresh tokens, so their session ends when the current access token expires.

A missing, malformed, or expired access token returns `401` (with `"Token has expired"` for the expired case, so clients know to refresh). A valid token for a role that is not allowed to do something returns `403`.

### Roles

| Role | Can |
| --- | --- |
| `employee` | File tickets, see their own tickets, message on them |
| `engineer` | Everything above, plus see and work tickets assigned to them |
| `facility_admin` | Everything, plus manage users, assign tickets, see all tickets |

New accounts are always `employee`. Roles are changed only by an admin via `PUT /api/users/{id}/role`.

### Who can see a ticket

A ticket, and its message thread, is visible to the person who reported it, the engineer assigned to it, and admins. Anyone else gets `404`, not `403` — the API does not confirm that a ticket exists to someone who has no access to it.

## Errors

Every error has the same shape:

```json
{ "error": "'priority' must be between 1 and 5" }
```

| Status | Meaning |
| --- | --- |
| `400` | Validation failed or the body is not valid JSON — the message names the field |
| `401` | Not signed in, or the token is invalid or expired |
| `403` | Signed in, but this role may not do this |
| `404` | No such record, or no access to it |
| `405` | Route exists but not for this method |
| `409` | Conflict with existing data (duplicate email, closed ticket, building in use) |
| `500` | Server or database error — details are in the Lambda logs, not the response |

Text fields are trimmed. Emails are stored lower-cased and matched case-insensitively.

---

## Users — `/api/users`

### `GET /api/users/branches` — the company branches

Public (no token), because the signup form needs it before anyone is signed in.

```json
[{ "id": 2, "name": "Miami" }, { "id": 1, "name": "Princeton-Plainsboro" }]
```

### `POST /api/users` — create an account

Public. Always creates an `employee`; a `role` in the body is ignored. The email must be a company address ending in `@acme.inc` (case-insensitive). `branchId` picks the branch the person works at.

```json
{ "email": "ana@acme.inc", "password": "at least 8 chars", "name": "Ana", "branchId": 1 }
```

`201` →
```json
{ "id": 1, "email": "ana@acme.inc", "name": "Ana", "role": "employee",
  "branch": { "id": 1, "name": "Princeton-Plainsboro" },
  "createdAt": "2026-09-22T14:03:11.412Z", "updatedAt": "2026-09-22T14:03:11.412Z" }
```

Every user object, here and elsewhere, carries `branch`.

Errors: `400` invalid email, email not ending in `@acme.inc`, password under 8 characters or over 72 bytes, missing name, missing or unknown `branchId` · `409` email already registered.

### `POST /api/users/login` — log in

Public.

```json
{ "email": "ana@acme.inc", "password": "..." }
```

`200` →
```json
{ "user": { "id": 1, "email": "ana@acme.inc", "name": "Ana", "role": "employee", "...": "..." },
  "token": "eyJhbGciOi...",
  "refreshToken": "Kq9c2m..." }
```

Errors: `401` wrong email or password (same message for both, deliberately).

### `POST /api/users/refresh` — get a new access token

Public (the refresh token is the credential).

```json
{ "refreshToken": "Kq9c2m..." }
```

`200` → the same shape as login: `user`, a new `token`, and a new `refreshToken`. The one you sent is revoked; use the new one next time. The new access token reflects the user's current role.

Errors: `400` missing refresh token · `401` unknown, already-used, expired, or revoked refresh token — sign in again.

### `POST /api/users/logout` — end a session

Public. Revokes the given refresh token so it cannot be used again. The client should also discard its access token.

```json
{ "refreshToken": "Kq9c2m..." }
```

`204`.

### `GET /api/users/me` — the signed-in user

`200` → the user object. `401` if the token's account has been deleted.

### `GET /api/users` — list accounts

Admin only. Returns the accounts at the **caller's own branch**; a facility admin never sees or manages another branch's people. Optional `?role=employee|engineer|facility_admin`, useful for the assign-ticket dropdown.

`200` → array of user objects, newest first.

### `PUT /api/users/{id}/role` — promote or demote

Admin only.

```json
{ "role": "engineer" }
```

`role` is one of `employee`, `engineer`, `facility_admin`. `200` → the updated user. The change applies to the user's next request immediately. If the change is a demotion, the user's refresh tokens are revoked as well.

Errors: `400` unknown role · `403` an admin changing their own role, or a user at another branch · `404` no such user.

### `DELETE /api/users/{id}` — delete an account

Admin only. `204` on success. Their refresh tokens and inbox read-marks are deleted with them.

Tickets they reported and messages they wrote are kept. On those, `reportedBy` / `author` becomes `null`, which the frontend shows as "Deleted user". A ticket assigned to them goes back to unassigned.

Errors: `403` deleting your own account, or a user at another branch · `404` no such user.

---

## Buildings — `/api/buildings`

Buildings belong to a branch. Everyone sees, and admins manage, only the buildings at their own branch.

### Building object

```json
{
  "id": 1, "branchId": 1, "name": "HQ",
  "floors": 3, "basementFloors": 2,
  "roomNumbersIncludeFloor": true,
  "rooms": [
    { "floor": 3, "rooms": 10 }, { "floor": 2, "rooms": 10 }, { "floor": 1, "rooms": 10 },
    { "floor": -1, "rooms": 4 }, { "floor": -2, "rooms": 0 }
  ],
  "createdAt": "…", "updatedAt": "…"
}
```

- `floors` is the number of above-ground floors (1–200), numbered `1..floors`.
- `basementFloors` (0–20) are numbered `-1..-basementFloors`; the app shows `-1` as **B1**, `-2` as **B2**.
- `rooms` lists every floor in display order (top floor first, then B1, B2, …) with how many rooms it has. `0` means not set: the ticket form then accepts any room number. Otherwise the ticket form offers rooms `1..rooms` and the API rejects anything higher.
- `roomNumbersIncludeFloor` (default `false`): when true, rooms are *written* with the floor in front. Room 1 on floor 5 is `501` while every floor has fewer than 100 rooms, and `5001` once any floor has 100 or more; on a basement floor it is `B101`. This only affects how rooms are displayed. The API always stores and accepts the plain room index (`"room": 1`), and ticket locations carry the written form in `roomLabel`. Turning the flag **on** converts existing tickets whose room was typed in that style: room `502` on floor 5 becomes index `2` (only when the leading digits equal the ticket's own floor; other rooms are left as they are).

### `GET /api/buildings` — list buildings

Any signed-in user. `200` → the buildings at the caller's branch, alphabetical.

### `POST /api/buildings` — add a building

Admin only; the building is created at the admin's branch.

```json
{ "name": "HQ", "floors": 3, "basementFloors": 2, "roomsPerFloor": 10, "rooms": [{ "floor": -1, "rooms": 4 }], "roomNumbersIncludeFloor": true }
```

`basementFloors` defaults to 0. Rooms can be given as `roomsPerFloor` (the same number on every floor), as `rooms` (a list of `{floor, rooms}` for some or all floors), or both — a floor's `rooms` entry wins over `roomsPerFloor`, and floors given neither get 0.

`201` → the building. Errors: `400` blank name, floors or rooms out of range, or `rooms` naming a floor the building does not have · `409` a building with that name (any case) already exists at this branch.

### `PUT /api/buildings/{id}` — rename, change floors or rooms

Admin only, own branch only. Send any of `name`, `floors`, `basementFloors`, `roomsPerFloor`, `rooms`, `roomNumbersIncludeFloor`; fields left out keep their value, and floors not mentioned keep their room count.

`200` → the building. Errors: `400` a floor or room count would drop below one a ticket already uses (the message says which) · `403` the building is at another branch · `404` no such building · `409` name taken at this branch.

### `DELETE /api/buildings/{id}` — remove a building

Admin only, own branch only. `204`. Errors: `403` another branch · `404` no such building · `409` tickets are located in it.

---

## Incidents — `/api/incidents`

### Ticket object

```json
{
  "id": 12,
  "title": "Leaking pipe",
  "description": "Under the sink in the 3rd floor kitchen",
  "status": "in_progress",
  "priority": 2,
  "location": { "id": 1, "building": { "id": 2, "name": "HQ" }, "floor": 3, "room": 12, "roomLabel": "312" },
  "reportedBy": { "id": 4, "name": "Ana", "email": "ana@acme.inc" },   // null if that account was deleted
  "assignedTo": { "id": 7, "name": "Bob", "email": "bob@example.com" },
  "createdAt": "2026-09-22T14:10:02.101Z",
  "updatedAt": "2026-09-22T15:42:37.880Z",
  "resolvedAt": null
}
```

- `status`: `open` → `assigned` → `in_progress` → `blocked` / `resolved` → `closed`. New tickets are `open`; assigning an engineer moves an open ticket to `assigned` automatically, and unassigning moves an `assigned` ticket back to `open`.
- `priority`: `1` (most urgent) to `5`. Defaults to `3`.
- `location`, `assignedTo`, `resolvedAt`, and `location.room` are `null` when not set. `floor` and `room` are numbers.
- `resolvedAt` is stamped automatically when status becomes `resolved` or `closed`, and cleared if the ticket is reopened.

### `POST /api/incidents` — file a ticket

Any signed-in user. The reporter is taken from the token.

```json
{
  "title": "Leaking pipe",
  "description": "optional",
  "priority": 2,
  "location": { "buildingId": 2, "floor": 3, "room": 12 }
}
```

`location` is optional. `buildingId` must be a building at your branch; `floor` is `1..floors` or `-1..-basementFloors` (no 0); `room` is an optional room index, at most the floor's room count when one is set. Responses add `roomLabel`, the room as the building writes it (`312` when it numbers rooms by floor, else `12`). The same place is stored once and reused by every ticket reported there.

`201` → the ticket.

Errors: `400` missing title, priority outside 1–5, unknown `buildingId` or one at another branch, floor outside the building's range (floors are `1..floors` and `-1..-basementFloors`; there is no 0), non-numeric room, or a room above the floor's room count.

### `GET /api/incidents` — list tickets

| Query | Who | Returns |
| --- | --- | --- |
| *(none)* or `?scope=mine` | anyone | tickets you reported |
| `?scope=assigned` | engineer, admin | tickets assigned to you |
| `?scope=unassigned` | admin | open tickets with no engineer |
| `?scope=all` | admin | every ticket |

Add `?status=` and/or `?priority=` to filter (not combined with `unassigned`). Sorted most urgent first, then newest.

`200` → array of tickets. `403` for a scope your role can't use.

### `GET /api/incidents/{id}` — one ticket

Reporter, assignee, or admin. `200` → the ticket, otherwise `404`.

### `PUT /api/incidents/{id}/assign` — assign to an engineer

Admin only.

```json
{ "assigneeId": 7 }
```

Send `"assigneeId": null` to unassign. The assignee must be an engineer or admin. An `open` ticket becomes `assigned`; an `assigned` ticket that is unassigned becomes `open` again; other statuses are left as they are.

Also posts a message on the ticket, from the caller, so the new assignee and the reporter see it in their inbox:

> Ticket #12: assigned to Bob

`200` → the ticket.

Errors: `400` missing `assigneeId`, unknown user, the user is an employee, or the ticket already has that assignment · `404` no such ticket.

### `PUT /api/incidents/{id}/status` — change status

The assigned engineer, or any admin.

```json
{ "status": "in_progress" }
```

Also posts a message on the ticket, from the caller, in the same transaction:

> Ticket #12: status changed to in progress

`200` → the ticket.

`open` and `assigned` follow the assignment: a ticket with an engineer cannot be set to `open`, and a ticket without one cannot be set to `assigned`.

Errors: `400` unknown status, the ticket is already in that status, `open` requested while an engineer is assigned, or `assigned` requested with no engineer · `403` an engineer who is not assigned to this ticket · `404` no such ticket.

### `PUT /api/incidents/{id}/priority` — change priority

The assigned engineer, or any admin.

```json
{ "priority": 1 }
```

Also posts a message on the ticket, from the caller, in the same transaction:

> Ticket #12: priority changed to 1

`200` → the ticket.

Errors: `400` priority missing or outside 1–5, or the ticket already has that priority · `403` an engineer who is not assigned to this ticket · `404` no such ticket.

### `PUT /api/incidents/{id}/location` — move the ticket

Admin only. Same `location` shape as when filing a ticket; send `"location": null` to clear it.

```json
{ "location": { "buildingId": 1, "floor": 4, "room": 7 } }
```

Also posts a message on the ticket, from the caller, in the same transaction:

> Ticket #12: location changed to HQ, floor 4, room 7

`200` → the ticket.

Errors: `400` `location` key missing, unknown `buildingId`, floor outside the building's range, non-numeric room, or the ticket already has that location · `403` not an admin · `404` no such ticket.

### `GET /api/incidents/stats/overview` — all tickets by status

Admin only. `?days=N` (default 30, max 365) counts tickets created in the last N days.

```json
{ "total": 42, "byStatus": { "open": 20, "in_progress": 9, "blocked": 3, "resolved": 6, "closed": 4 } }
```

Every status is always present, with `0` when empty. Errors: `400` days outside 1–365 · `403` not an admin.

### `GET /api/incidents/stats/locations` — tickets per building, floor or room

Admin only, same `?days=` as above. Drill down by adding parameters:

| Query | `level` | `items` |
|---|---|---|
| none | `building` | `[{ "id": 1, "name": "HQ", "count": 7 }, { "id": null, "name": "No location", "count": 2 }]` |
| `?buildingId=1` | `floor` | `[{ "floor": 3, "count": 4 }]`, plus `building: { id, name }` |
| `?buildingId=1&floor=3` | `room` | `[{ "room": 12, "label": "312", "count": 2 }, { "room": null, "label": null, "count": 1 }]`, plus `building` and `floor` |

Buildings are sorted by count, floors and rooms by number. `null` room means the ticket gave no room. Errors: `400` bad parameter · `403` not an admin · `404` unknown building.

### `GET /api/incidents/stats/mine` — the caller's own tickets by status

Any signed-in user, same `?days=`.

```json
{
  "reported": { "total": 5, "byStatus": { "open": 2, "in_progress": 1, "blocked": 0, "resolved": 1, "closed": 1 } },
  "assigned": null
}
```

`reported` counts tickets the caller filed. `assigned` counts tickets assigned to the caller and is `null` for employees.

---

## Messages — `/api/messages`

### Message object

```json
{
  "id": 31,
  "incidentId": 12,
  "message": "On my way up.",
  "author": { "id": 7, "name": "Bob", "email": "bob@example.com", "role": "engineer" },   // null if that account was deleted
  "createdAt": "2026-09-22T15:44:09.216Z",
  "updatedAt": "2026-09-22T15:44:09.216Z"
}
```

Status and assignment changes appear in the thread as ordinary messages authored by whoever made the change.

### `POST /api/messages` — post on a ticket

Reporter, assignee, or admin of that ticket. The author is taken from the token.

```json
{ "incidentId": 12, "message": "On my way up." }
```

`201` → the message.

Errors: `400` empty message or over 5000 characters · `404` no such ticket or no access · `409` the ticket is `closed` — reopen it to continue the thread.

### `GET /api/messages?incidentId={id}` — read a thread

Reporter, assignee, or admin of that ticket.

`200` → array of messages, oldest first. `400` without `incidentId`. `404` no such ticket or no access.

---

## Inbox — `/api/inbox`

What the signed-in user has not seen yet. A message is **unread** when it is on a ticket you reported or are assigned to, someone else wrote it, and it is newer than the last time you opened that ticket. Status and assignment changes are recorded as messages, so they show up here too. Your own messages never count.

The inbox is personal: there is no way to read or change anyone else's, and admins get no special view.

### `GET /api/inbox` — tickets with unread activity

`200` →
```json
{
  "unread": 3,
  "items": [
    {
      "incident": { "id": 12, "title": "Leaking pipe", "status": "in_progress", "priority": 2 },
      "unreadCount": 2,
      "latestMessage": {
        "message": "Ticket #12: status changed to in progress",
        "createdAt": "2026-09-22T15:42:37.880Z",
        "author": { "id": 7, "name": "Bob" }
      }
    }
  ]
}
```

Sorted by most recent unread activity. `unread` is the total across all items.

### `GET /api/inbox/count` — unread total only

Cheap enough to poll for a badge. `200` → `{ "unread": 3 }`

### `PUT /api/inbox/{incidentId}/read` — mark one ticket read

Call it when the user opens a ticket. Allowed for the reporter, the assignee, or an admin; anyone else gets `404`.

`200` → `{ "incidentId": 12, "lastReadAt": "...", "unread": 1 }` — `unread` is the caller's remaining total, so a badge can update without a second request.

### `PUT /api/inbox/read-all` — mark everything read

`200` → `{ "unread": 0 }`

---

## Migrations — `/api/migrations`

Creates any missing database tables. The schema is the `SCHEMA` list at the top of `backend/migrations/function.py`. Every statement uses `IF NOT EXISTS`, so calling this repeatedly is safe.

| Method | Does |
| --- | --- |
| `POST` | Apply the schema. `200` → `{ "message": "Schema applied", "tables": ["users", "buildings", "locations", "incidents", "messages", "refresh_tokens", "ticket_reads"] }` |
| `GET` | Report which tables exist. `200` → `{ "tables": [...], "missing": [...] }` |

This endpoint is currently unauthenticated. It only ever creates — nothing is dropped — but add a shared-secret check before exposing it outside the workshop.

---

## Quick walkthrough

```sh
API=http://localhost:3001

# Set up
curl -s -X POST $API/api/migrations

# Sign up and log in
curl -s -X POST $API/api/users -H 'Content-Type: application/json' \
  -d '{"email":"ana@acme.inc","password":"hunter22!","name":"Ana"}'
TOKEN=$(curl -s -X POST $API/api/users/login -H 'Content-Type: application/json' \
  -d '{"email":"ana@acme.inc","password":"hunter22!"}' | jq -r .token)

# File a ticket (buildingId from GET /api/buildings, which an admin populates first)
curl -s -X POST $API/api/incidents -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"Leaking pipe","priority":2,"location":{"buildingId":1,"floor":3,"room":12}}'   # floor -1 would be B1

# See your tickets
curl -s $API/api/incidents -H "Authorization: Bearer $TOKEN"

# Post on ticket 1
curl -s -X POST $API/api/messages -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"incidentId":1,"message":"It is getting worse."}'
```
