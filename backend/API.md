# Incident Tracker API

> **Changed 2026-09-24 (breaking):** `GET /api/incidents`, `GET /api/users` and `GET /api/messages` return one page as an object (`{items, total, ...}`) instead of a bare array, and take paging, search and sort parameters. See [Lists and pages](#lists-and-pages). Clients written for the array shape must read `items`.

Six Lambda services behind `/api/`: `users`, `buildings`, `incidents`, `messages`, `inbox`, and `migrations`. All requests and responses are JSON.

| Environment | Base URL |
| --- | --- |
| Local (`./bin/start-dev.sh`) | `http://localhost:3001` |
| Cloud (`./bin/deploy-backend.sh`) | `https://{API_BASE_URL}` — printed by the deploy script |

## Setup

1. Start the environment: `./bin/start-dev.sh`
2. Create the tables: `curl -X POST http://localhost:3001/api/migrations` (open on a fresh database; afterwards it needs the db admin's token, see Migrations)
3. Sign in as the db admin the migration created (`admin@admin.com` / `admin123`), open the Employee directory, and promote your facility admins. Everyone else signs up through the site and is promoted by their branch's facility admin.

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
|---|---|
| `employee` | File tickets, see and message on their own tickets |
| `engineer` | Everything above, plus work tickets assigned to them |
| `facility_admin` | Everything **at their branch**: every ticket filed there, assignment (to staff at that branch), statistics, buildings, and the accounts (any role except `db_admin`). Tickets at another branch are invisible to them, as if they did not exist |
| `db_admin` | Manage accounts and roles across **every branch**, including `facility_admin` and `db_admin`, and run the migration. Not facilities staff: no ticket or building powers beyond an employee's |

Signup always creates an `employee`. One `db_admin` account is created by the migration on every deployment: `admin@admin.com` / `admin123`, name `admin`, at Princeton-Plainsboro. (Fixed on purpose for this workshop project; in a real system the first admin is created by someone with direct database access and the password comes from a secret.)

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

## Lists and pages

No list endpoint ever returns everything. `GET /api/incidents` and `GET /api/users` take `?page=N&limit=M` (page 1 of 25 by default, limit at most 100) and answer one page plus the count:

```json
{ "items": [ ... ], "total": 137, "page": 2, "limit": 25, "pages": 6 }
```

`pages` is at least 1, so "page 1 of 1" reads right for an empty list; a page past the end has empty `items` and the real `total`. Both endpoints also take `?q=` (a text search: every word must appear, in any order, ignoring case), `?sort=` and `?order=asc|desc`. Every order ends with the record's id as a tie-breaker, so a row can never appear on two pages or on neither. The database does the limiting, so a page costs the same however large the table grows.

A ticket's thread (`GET /api/messages`) is paged differently, by cursor, because it is read newest-first and messages keep arriving while it is open: see that endpoint.

Errors: `400` `'page' must be between 1 and 1000000`, `'limit' must be between 1 and 100`, `'sort' must be one of: ...`, `'order' must be one of: asc, desc`, `'q' must be 100 characters or fewer`.

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

### `GET /api/users` — one page of accounts

Facility admin or db admin. A facility admin gets the accounts at their **own branch**; a db admin gets **every branch**, or one with `?branchId=`.

| Query | Meaning |
| --- | --- |
| `role=engineer` | one role; several with commas: `role=engineer,facility_admin` (the assign-ticket dropdown) |
| `q=ana` | name or email contains every word |
| `sort=created` (default, newest first), `name`, `role` (most senior first) | with `order=asc|desc` |
| `page=`, `limit=` | see [Lists and pages](#lists-and-pages) |

`200` → `{ "items": [user objects], "total", "page", "limit", "pages" }`.

Errors: `400` unknown role, sort or order, or a bad page/limit/branchId.

### `PUT /api/users/{id}/role` — promote or demote

Admin only.

```json
{ "role": "engineer" }
```

`role` is one of `employee`, `engineer`, `facility_admin`. `200` → the updated user. The change applies to the user's next request immediately. If the change is a demotion, the user's refresh tokens are revoked as well.

A facility admin may set `employee`, `engineer` or `facility_admin` for people at their branch, never touching a `db_admin` account. A db admin may set any role for anyone.

Errors: `400` unknown role, or a facility admin sending `db_admin` · `403` changing your own role, a user at another branch, or a facility admin changing a db admin · `404` no such user.

### `DELETE /api/users/{id}` — delete an account

Admin only. `204` on success. Their refresh tokens and inbox read-marks are deleted with them.

Tickets they reported and messages they wrote are kept. On those, `reportedBy` / `author` becomes `null`, which the frontend shows as "Deleted user". A ticket assigned to them goes back to unassigned.

Errors: `403` deleting your own account, a user at another branch, or a facility admin deleting a db admin · `404` no such user.

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
  "category": "plumbing",
  "location": { "id": 1, "building": { "id": 2, "name": "HQ" }, "floor": 3, "room": 12, "roomLabel": "312" },
  "branchId": 1,                                                        // the branch the ticket was filed at (the reporter's)
  "reportedBy": { "id": 4, "name": "Ana", "email": "ana@acme.inc" },   // null if that account was deleted
  "assignedTo": { "id": 7, "name": "Bob", "email": "bob@example.com" },
  "createdAt": "2026-09-22T14:10:02.101Z",
  "updatedAt": "2026-09-22T15:42:37.880Z",
  "resolvedAt": null
}
```

- `status`: `open` → `assigned` → `in_progress` → `blocked` / `resolved` → `closed`. New tickets are `open`; assigning an engineer moves an open ticket to `assigned` automatically, and unassigning moves an `assigned` ticket back to `open`.
- `priority`: `1` (most urgent) to `5`. Defaults to `3`.
- `category`: what kind of problem it is, one of `plumbing`, `electrical`, `hvac` (heating, ventilation and air conditioning), `structural`, `doors_and_locks`, `elevators`, `furniture`, `appliances`, `safety`, `cleaning`, `other`. Defaults to `other`. The list lives in `backend/incidents/models/incident.py` and as the CHECK rule on the column.
- `location`, `assignedTo`, `resolvedAt`, and `location.room` are `null` when not set. `floor` and `room` are numbers.
- `resolvedAt` is stamped automatically when status becomes `resolved` or `closed`, and cleared if the ticket is reopened.

### `POST /api/incidents` — file a ticket

Any signed-in user. The reporter is taken from the token.

```json
{
  "title": "Leaking pipe",
  "description": "optional",
  "priority": 2,
  "category": "plumbing",
  "location": { "buildingId": 2, "floor": 3, "room": 12 }
}
```

`category` is optional and defaults to `other`. `location` is optional. `buildingId` must be a building at your branch; `floor` is `1..floors` or `-1..-basementFloors` (no 0); `room` is an optional room index, at most the floor's room count when one is set. Responses add `roomLabel`, the room as the building writes it (`312` when it numbers rooms by floor, else `12`). The same place is stored once and reused by every ticket reported there.

`201` → the ticket.

Errors: `400` missing title, priority outside 1–5, a `category` outside the list (`'category' must be one of: plumbing, electrical, ...`), unknown `buildingId` or one at another branch, floor outside the building's range (floors are `1..floors` and `-1..-basementFloors`; there is no 0), non-numeric room, or a room above the floor's room count.

### `GET /api/incidents` — one page of tickets

| Query | Who | Returns |
| --- | --- | --- |
| *(none)* or `?scope=mine` | anyone | tickets you reported |
| `?scope=assigned` | engineer, admin | tickets assigned to you |
| `?scope=unassigned` | admin | unfinished tickets with no engineer, at your branch |
| `?scope=pending` | admin | tickets with a blocked/resolved request awaiting approval, at your branch |
| `?scope=all` | admin | every ticket at your branch |

A ticket belongs to the branch it was filed at (`branchId`, the reporter's branch). The three admin scopes never show another branch's tickets: a Miami admin sees Miami's queue only.

Narrow any scope further:

| Query | Meaning |
| --- | --- |
| `status=open`, `priority=2`, `category=plumbing` | one status, one priority, one category |
| `status=open,in_progress` | tickets in any of the listed statuses |
| `days=14` | created in the last N days (1–365); the site uses 14 by default |
| `buildingId=2` | in one building (it must be at your branch) |
| `buildingId=2&floor=3` | on one floor of it (`floor=-1` is B1); `floor` needs `buildingId` and must be a floor the building has |
| `q=leak kitchen` | every word appears in the title, description, reporter's or assignee's name, or building name; a word like `#12` or `12` also matches the ticket number |
| `sort=priority` (default: most urgent first, then newest), `created`, `updated`, `id`, `title`, `location` (building, floor, room; tickets with no location last) | with `order=asc|desc` |
| `page=`, `limit=` | see [Lists and pages](#lists-and-pages) |

`200` → `{ "items": [tickets], "total", "page", "limit", "pages" }`. `403` for a scope your role can't use. `400` `'buildingId' must be a positive whole number`, `'buildingId' does not match a known building`, `'buildingId' is not a building at your branch`, `'floor' needs a 'buildingId'`, `'floor' must be between B1 and 3 (there is no floor 0)`.

The Approvals badge asks for `?scope=pending&limit=1` and reads `total`: the cheapest way to count.

### `GET /api/incidents/{id}` — one ticket

Reporter, assignee, or admin. `200` → the ticket, otherwise `404`.

### `PUT /api/incidents/{id}/assign` — assign to an engineer

Admin only.

```json
{ "assigneeId": 7 }
```

Send `"assigneeId": null` to unassign. The assignee must be an engineer or admin **at the ticket's branch** (the assign dropdown lists your branch's staff, so this only matters for hand-made requests). An `open` ticket becomes `assigned`; an `assigned` ticket that is unassigned becomes `open` again; other statuses are left as they are.

Also posts a message on the ticket, from the caller, so the new assignee and the reporter see it in their inbox:

> Ticket #12: assigned to Bob

`200` → the ticket.

Errors: `400` missing `assigneeId`, unknown user, the user is an employee, the user works at another branch (`Tickets can only be assigned to staff at the ticket's branch`), or the ticket already has that assignment · `404` no such ticket, or a ticket at another branch.

### `PUT /api/incidents/{id}/status` — change status

The assigned engineer, or any admin.

```json
{ "status": "in_progress", "note": "optional, added to the thread message" }
```

**Approval rule.** An engineer asking for `blocked` or `resolved` does not change the status. The request is stored on the ticket as `pendingApproval` (`{ status, note, requestedAt, requestedBy }`), a message "Ticket #12: requested resolved, awaiting facility admin approval" is posted, and a facility admin decides with the approval endpoint below. Admins setting those statuses apply them immediately. Any real status change clears a pending request.

Also posts a message on the ticket, from the caller, in the same transaction:

> Ticket #12: status changed to in progress

`200` → the ticket.

`open` and `assigned` follow the assignment: a ticket with an engineer cannot be set to `open`, and a ticket without one cannot be set to `assigned`.

Errors: `400` unknown status, the ticket is already in that status, the same request is already pending, `open` requested while an engineer is assigned, or `assigned` requested with no engineer · `403` an engineer who is not assigned to this ticket · `404` no such ticket, or an admin at another branch.

### `PUT /api/incidents/{id}/approval` — approve or reject a request

Admin only.

```json
{ "decision": "approve", "note": "optional" }
```

`approve` applies the requested status (stamping `resolvedAt` for resolved) and posts "Ticket #12: status changed to resolved (approved)". `reject` clears the request and posts "Ticket #12: request to mark resolved rejected". Either message carries the note.

`200` → the ticket. Errors: `400` unknown decision, or nothing pending · `403` not an admin · `404` no such ticket, or a ticket at another branch.

### `PUT /api/incidents/{id}/priority` — change priority

The assigned engineer, or any admin.

```json
{ "priority": 1 }
```

Also posts a message on the ticket, from the caller, in the same transaction:

> Ticket #12: priority changed to 1

`200` → the ticket.

Errors: `400` priority missing or outside 1–5, or the ticket already has that priority · `403` an engineer who is not assigned to this ticket · `404` no such ticket, or an admin at another branch.

### `PUT /api/incidents/{id}/category` — change category

Assigned engineer or admin (same rules as priority).

```json
{ "category": "hvac" }
```

Adds a message to the thread, using the name people read (`hvac` is written `AC / heating`):

> Ticket #12: category changed to AC / heating

`200` → the ticket.

Errors: `400` category missing or outside the list, or the ticket is already in that category (`Incident is already in the plumbing category`) · `403` an engineer who is not assigned to this ticket · `404` no such ticket, or an admin at another branch.

### `PUT /api/incidents/{id}/location` — move the ticket

Admin only. Same `location` shape as when filing a ticket; send `"location": null` to clear it.

```json
{ "location": { "buildingId": 1, "floor": 4, "room": 7 } }
```

Also posts a message on the ticket, from the caller, in the same transaction:

> Ticket #12: location changed to HQ, floor 4, room 7

`200` → the ticket.

Errors: `400` `location` key missing, unknown `buildingId`, floor outside the building's range, non-numeric room, or the ticket already has that location · `403` not an admin · `404` no such ticket, or a ticket at another branch.

### `GET /api/incidents/stats/overview` — the branch's tickets by status, priority and category

Admin only, and only the tickets at the admin's own branch. `?days=N` (default 30, max 365) counts tickets created in the last N days.

```json
{
  "total": 42,
  "byStatus": { "open": 20, "assigned": 5, "in_progress": 9, "blocked": 3, "resolved": 3, "closed": 2 },
  "byPriority": { "1": 4, "2": 7, "3": 20, "4": 6, "5": 5 },
  "byCategory": { "plumbing": 9, "electrical": 7, "hvac": 6, "structural": 5, "doors_and_locks": 3, "elevators": 1, "furniture": 4, "appliances": 3, "safety": 2, "cleaning": 1, "other": 1 },
  "resolution": { "averageSeconds": 93600.0, "resolvedCount": 5 }
}
```

`byPriority` runs from 1 (most urgent) to 5 and, like `byStatus`, always lists every value (feeds the priority chart on the Statistics page). `byCategory` lists every category in the order of the ticket object's list, with `0` when empty (feeds the category ring on the Statistics page).

Every status is always present, with `0` when empty. `resolution` averages `resolvedAt - createdAt` over the tickets in the range that have been resolved; `averageSeconds` is `null` when none have. Errors: `400` days outside 1–365 · `403` not an admin.

### `GET /api/incidents/stats/locations` — tickets per building, floor or room

Admin only, same `?days=` as above. Drill down by adding parameters:

| Query | `level` | `items` |
|---|---|---|
| none | `building` | `[{ "id": 1, "name": "HQ", "count": 7 }, { "id": null, "name": "No location", "count": 2 }]` |
| `?buildingId=1` | `floor` | `[{ "floor": 3, "count": 4 }]`, plus `building: { id, name }` |
| `?buildingId=1&floor=3` | `room` | `[{ "room": 12, "label": "312", "count": 2 }, { "room": null, "label": null, "count": 1 }]`, plus `building` and `floor` |

Only the admin's own branch is counted, and `buildingId` must be a building there. Buildings are sorted by count, floors and rooms by number. `null` room means the ticket gave no room. Errors: `400` bad parameter · `403` not an admin · `404` unknown building, or one at another branch.

### `GET /api/incidents/stats/engineers` — per-engineer workload

Admin only, same `?days=`. One row per engineer or admin with tickets assigned in the range, most loaded first.

```json
[{ "id": 7, "name": "Hugh Laurie", "role": "engineer", "assigned": 13, "resolved": 4, "averageSeconds": 5400.0 }]
```

`assigned` counts tickets currently assigned to them, `resolved` those with a resolved time, `averageSeconds` their average creation-to-resolution time (`null` if none resolved).

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

### `GET /api/messages?incidentId={id}` — one page of a thread

Reporter, assignee, or admin of that ticket.

Without more parameters: the **newest 50** messages, returned oldest first so they read top to bottom, with how many the ticket has in all and whether older ones exist:

```json
{ "items": [ ... ], "total": 137, "hasMore": true }
```

| Query | Meaning |
| --- | --- |
| `limit=50` | page size, at most 200 |
| `before=<message id>` | the page of older messages ending just before that message: pass the id of the oldest message you have to load the next page up |

This is keyset pagination rather than page numbers: a page is defined by where the previous one ended, so a message posted while someone is reading never shifts the pages or shows up twice.

`400` without `incidentId`, or a bad `limit`/`before`. `404` no such ticket or no access.

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

It also creates the `db_admin` account (see Roles) and seeds the two branches.

**Who may call it.** The first run on a fresh database is open, because it is what creates the users table and the db admin. From then on both `GET` and `POST` require a db admin's access token (`401` without one, `403` for any other role):

```sh
TOKEN=$(curl -s -X POST $API/api/users/login -H "Content-Type: application/json" \
  -d '{"email":"admin@admin.com","password":"admin123"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
curl -s -X POST $API/api/migrations -H "Authorization: Bearer $TOKEN"
```

### `POST /api/migrations/seed` — load the sample data (temporary)

Db admin only. **Replaces** every account, building, ticket and message with the sample set in `backend/migrations/seed.sql` (the local development data: the House cast accounts, buildings A/B/C at Princeton-Plainsboro with 81 tickets, the Dexter cast at Miami with 8 tickets in the Violent Crimes building, 18 tickets assigned in all and the rest open; resolved tickets took from about an hour to six days; every ticket has a category chosen from its title, so the category chart has a spread). Sessions are cleared too, so log in again afterwards. Branches are untouched. The id counters are moved past the loaded ids (the migration does the same on every run), so rows added afterwards never collide with the sample set.

```sh
curl -s -X POST $API/api/migrations/seed -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"confirm":"RESET"}'
```

`200` → `{ "message": "Sample data loaded", "rows": { "users": 13, "incidents": 89, ... } }`. Errors: `400` without `"confirm": "RESET"` · `401`/`403` not a db admin.

This exists for the workshop deployment only; real sample data belongs in test fixtures.

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

# See your tickets (the first page of 25; add ?page=2, ?q=leak, ?sort=created&order=desc)
curl -s $API/api/incidents -H "Authorization: Bearer $TOKEN"

# Post on ticket 1
curl -s -X POST $API/api/messages -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"incidentId":1,"message":"It is getting worse."}'
```
