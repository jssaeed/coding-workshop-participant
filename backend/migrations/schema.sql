-- Schema for the incident tracking application.
--
-- This script is idempotent: every statement uses IF NOT EXISTS or CREATE OR
-- REPLACE, so it is safe to run repeatedly against the same database.

-- ---------------------------------------------------------------------------
-- Helper: keep updated_at in sync on every UPDATE
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         TEXT        NOT NULL,
    password_hash TEXT        NOT NULL,
    name          TEXT        NOT NULL CHECK (name <> ''),
    role          TEXT        NOT NULL DEFAULT 'employee'
                              CHECK (role IN ('facility_admin', 'engineer', 'employee')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Email uniqueness is case-insensitive: Foo@x.com and foo@x.com are one user.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_key ON users (LOWER(email));

DROP TRIGGER IF EXISTS users_set_updated_at ON users;
CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- locations
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS locations (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building   TEXT        NOT NULL CHECK (building <> ''),
    floor      TEXT        NOT NULL CHECK (floor <> ''),
    -- Empty string rather than NULL so the UNIQUE constraint below still
    -- rejects duplicates when no room is given.
    room       TEXT        NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT locations_unique_place UNIQUE (building, floor, room)
);

DROP TRIGGER IF EXISTS locations_set_updated_at ON locations;
CREATE TRIGGER locations_set_updated_at
    BEFORE UPDATE ON locations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- incidents
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS incidents (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT        NOT NULL CHECK (title <> ''),
    description TEXT        NOT NULL DEFAULT '',
    status      TEXT        NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'in_progress', 'blocked', 'resolved', 'closed')),
    priority    SMALLINT    NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),

    location_id BIGINT      REFERENCES locations (id) ON DELETE RESTRICT,

    -- Who filed it. Kept on RESTRICT so deleting a user cannot silently erase
    -- the origin of an incident.
    reported_by BIGINT      NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    -- Which engineer owns it. NULL means unassigned; SET NULL returns the
    -- incident to the unassigned queue if the engineer's account is removed.
    assigned_to BIGINT      REFERENCES users (id) ON DELETE SET NULL,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- Filter/sort columns used by the list endpoints.
CREATE INDEX IF NOT EXISTS incidents_status_idx      ON incidents (status);
CREATE INDEX IF NOT EXISTS incidents_priority_idx    ON incidents (priority);
CREATE INDEX IF NOT EXISTS incidents_created_at_idx  ON incidents (created_at DESC);
CREATE INDEX IF NOT EXISTS incidents_location_id_idx ON incidents (location_id);
CREATE INDEX IF NOT EXISTS incidents_reported_by_idx ON incidents (reported_by);
CREATE INDEX IF NOT EXISTS incidents_assigned_to_idx ON incidents (assigned_to);

-- Stamp resolved_at the moment an incident reaches a terminal status, and
-- clear it if the incident is reopened, so the column cannot drift from status.
CREATE OR REPLACE FUNCTION set_incident_resolved_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status IN ('resolved', 'closed') THEN
        IF NEW.resolved_at IS NULL THEN
            NEW.resolved_at = NOW();
        END IF;
    ELSE
        NEW.resolved_at = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS incidents_set_resolved_at ON incidents;
CREATE TRIGGER incidents_set_resolved_at
    BEFORE INSERT OR UPDATE OF status ON incidents
    FOR EACH ROW EXECUTE FUNCTION set_incident_resolved_at();

DROP TRIGGER IF EXISTS incidents_set_updated_at ON incidents;
CREATE TRIGGER incidents_set_updated_at
    BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- messages
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS messages (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Messages belong to their incident: deleting the incident deletes the
    -- thread, which would otherwise be orphaned.
    incident_id BIGINT      NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    user_id     BIGINT      NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    message     TEXT        NOT NULL CHECK (message <> ''),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Threads are always read as "all messages for one incident, oldest first".
CREATE INDEX IF NOT EXISTS messages_incident_id_created_at_idx
    ON messages (incident_id, created_at);
CREATE INDEX IF NOT EXISTS messages_user_id_idx ON messages (user_id);

DROP TRIGGER IF EXISTS messages_set_updated_at ON messages;
CREATE TRIGGER messages_set_updated_at
    BEFORE UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- ticket_reads: per-user "read up to here" watermark for each ticket's thread
-- ---------------------------------------------------------------------------
-- A message is unread for a user when it is newer than their watermark on
-- that ticket (or they have no watermark yet). One row per user per ticket
-- keeps this small regardless of how long threads get.

CREATE TABLE IF NOT EXISTS ticket_reads (
    user_id      BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    incident_id  BIGINT      NOT NULL REFERENCES incidents (id) ON DELETE CASCADE,
    last_read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, incident_id)
);

-- The inbox query starts from the user, so the primary key already serves it;
-- this covers the cascade when an incident is deleted.
CREATE INDEX IF NOT EXISTS ticket_reads_incident_id_idx ON ticket_reads (incident_id);
