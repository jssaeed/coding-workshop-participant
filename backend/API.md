# Incident Tracker API

Four Lambda services behind `/api/`: `users`, `incidents`, `messages`, and `migrations`. All requests and responses are JSON.

| Environment | Base URL |
| --- | --- |
| Local (`./bin/start-dev.sh`) | `http://localhost:3001` |
| Cloud (`./bin/deploy-backend.sh`) | `https://{API_BASE_URL}` — printed by the deploy script |

## Setup

1. Start the environment: `./bin/start-dev.sh`
2. Create the tables: `curl -X POST http://localhost:3001/api/migrations`
3. Sign up your first user (see `POST /api/users`), then make them an admin directly in the database — signup only ever creates employees, and only an admin can promote:
   ```sh
   psql -h localhost -U postgres -c "UPDATE users SET role = 'facility_admin' WHERE email = 'you@example.com'"
   ```
   Every later admin is promoted through the API.

Shared code lives in `backend/_shared/` and is copied into each service's `lib/` by `./bin/sync-shared.sh`. Run that script after editing anything in `_shared/` and commit the resulting `lib/` files — they are what deploys.

## Authentication

Log in to get a token, then send it on every other request:

```
Authorization: Bearer <token>
```

Tokens expire after 12 hours; log in again to get a new one. There is no refresh endpoint.

A missing, malformed, or expired token returns `401`. A valid token for a role that is not allowed to do something returns `403`.

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
| `409` | Conflict with existing data (duplicate email, closed ticket, user still referenced) |
| `500` | Server or database error — details are in the Lambda logs, not the response |

Text fields are trimmed. Emails are stored lower-cased and matched case-insensitively.

---

## Users — `/api/users`

### `POST /api/users` — create an account

Public. Always creates an `employee`; a `role` in the body is ignored.

```json
{ "email": "ana@example.com", "password": "at least 8 chars", "name": "Ana" }
```

`201` →
```json
{ "id": 1, "email": "ana@example.com", "name": "Ana", "role": "employee",
  "createdAt": "2026-09-22T14:03:11.412Z", "updatedAt": "2026-09-22T14:03:11.412Z" }
```

Errors: `400` invalid email, password under 8 characters or over 72 bytes, missing name · `409` email already registered.

### `POST /api/users/login` — log in

Public.

```json
{ "email": "ana@example.com", "password": "..." }
```

`200` →
```json
{ "user": { "id": 1, "email": "ana@example.com", "name": "Ana", "role": "employee", "...": "..." },
  "token": "eyJhbGciOi..." }
```

Errors: `401` wrong email or password (same message for both, deliberately).

### `GET /api/users/me` — the signed-in user

`200` → the user object. `401` if the token's account has been deleted.

### `GET /api/users` — list accounts

Admin only. Optional `?role=employee|engineer|facility_admin`, useful for the assign-ticket dropdown.

`200` → array of user objects, newest first.

### `PUT /api/users/{id}/role` — promote or demote

Admin only.

```json
{ "role": "engineer" }
```

`role` is one of `employee`, `engineer`, `facility_admin`. `200` → the updated user.

Errors: `400` unknown role · `403` an admin changing their own role · `404` no such user.

### `DELETE /api/users/{id}` — delete an account

Admin only. `204` on success.

Errors: `403` deleting your own account · `404` no such user · `409` the user has reported tickets or written messages — that history is kept, so the account cannot be removed.

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
  "location": { "id": 1, "building": "HQ", "floor": "3", "room": "Kitchen" },
  "reportedBy": { "id": 4, "name": "Ana", "email": "ana@example.com" },
  "assignedTo": { "id": 7, "name": "Bob", "email": "bob@example.com" },
  "createdAt": "2026-09-22T14:10:02.101Z",
  "updatedAt": "2026-09-22T15:42:37.880Z",
  "resolvedAt": null
}
```

- `status`: `open` → `in_progress` → `blocked` / `resolved` → `closed`. New tickets are `open`.
- `priority`: `1` (most urgent) to `5`. Defaults to `3`.
- `location`, `assignedTo`, `resolvedAt`, and `location.room` are `null` when not set.
- `resolvedAt` is stamped automatically when status becomes `resolved` or `closed`, and cleared if the ticket is reopened.

### `POST /api/incidents` — file a ticket

Any signed-in user. The reporter is taken from the token.

```json
{
  "title": "Leaking pipe",
  "description": "optional",
  "priority": 2,
  "location": { "building": "HQ", "floor": "3", "room": "Kitchen" }
}
```

`location` is optional. Pass either an object (an existing matching location is reused; `room` is optional) or `"locationId": 1` for a known one.

`201` → the ticket.

Errors: `400` missing title, priority outside 1–5, location missing building or floor, unknown `locationId`.

### `GET /api/incidents` — list tickets

| Query | Who | Returns |
| --- | --- | --- |
| *(none)* or `?scope=mine` | anyone | tickets you reported |
| `?scope=assigned` | engineer, admin | tickets assigned to you |
| `?scope=unassigned` | admin | open tickets with no engineer |
| `?scope=all` | admin | every ticket |

Add `?status=` and/or `?priority=` to filter (not combined with `unassigned`). Sorted most urgent first, then newest.

`200` → array of tickets. `403` for a scope your role can't use.

### `GET /api/incidents/locations` — known locations

Any signed-in user. For the report-a-ticket form.

`200` → `[{ "id": 1, "building": "HQ", "floor": "3", "room": "Kitchen" }, ...]`

### `GET /api/incidents/{id}` — one ticket

Reporter, assignee, or admin. `200` → the ticket, otherwise `404`.

### `PUT /api/incidents/{id}/assign` — assign to an engineer

Admin only.

```json
{ "assigneeId": 7 }
```

Send `"assigneeId": null` to unassign. The assignee must be an engineer or admin.

`200` → the ticket.

Errors: `400` missing `assigneeId`, unknown user, or the user is an employee · `404` no such ticket.

### `PUT /api/incidents/{id}/status` — change status

The assigned engineer, or any admin.

```json
{ "status": "in_progress" }
```

Also posts a message on the ticket, from the caller, in the same transaction:

> Ticket #12: status changed to in progress

`200` → the ticket.

Errors: `400` unknown status, or the ticket is already in that status · `403` an engineer who is not assigned to this ticket · `404` no such ticket.

---

## Messages — `/api/messages`

### Message object

```json
{
  "id": 31,
  "incidentId": 12,
  "message": "On my way up.",
  "author": { "id": 7, "name": "Bob", "email": "bob@example.com", "role": "engineer" },
  "createdAt": "2026-09-22T15:44:09.216Z",
  "updatedAt": "2026-09-22T15:44:09.216Z"
}
```

Status changes appear in the thread as ordinary messages authored by whoever made the change.

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

## Migrations — `/api/migrations`

Creates or updates the database tables from `backend/migrations/schema.sql`. The script is idempotent, so calling it repeatedly is safe.

| Method | Does |
| --- | --- |
| `POST` | Apply the schema. `200` → `{ "message": "Schema applied", "tables": ["users", "locations", "incidents", "messages"] }` |
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
  -d '{"email":"ana@example.com","password":"hunter22!","name":"Ana"}'
TOKEN=$(curl -s -X POST $API/api/users/login -H 'Content-Type: application/json' \
  -d '{"email":"ana@example.com","password":"hunter22!"}' | jq -r .token)

# File a ticket
curl -s -X POST $API/api/incidents -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"Leaking pipe","priority":2,"location":{"building":"HQ","floor":"3"}}'

# See your tickets
curl -s $API/api/incidents -H "Authorization: Bearer $TOKEN"

# Post on ticket 1
curl -s -X POST $API/api/messages -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"incidentId":1,"message":"It is getting worse."}'
```
