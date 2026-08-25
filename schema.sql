-- Schema for notes -> critic -> knowledge base -> output pipeline.
-- Matches DESIGN.md section 5. Run automatically by docker-compose on first init.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector, embedding columns + similarity search

-- Identity via OAuth only. No password column exists anywhere in this schema.
-- Note: this table intentionally has no RLS policy. Login (OAuth callback) has
-- to look the user up by oauth_subject_id BEFORE a user context exists to scope
-- a policy against -- a chicken-and-egg problem. Handled instead by keeping the
-- login lookup as a narrow, explicit query in the app layer, not by RLS.
CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    oauth_provider   TEXT NOT NULL,
    oauth_subject_id TEXT NOT NULL,
    display_name     TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (oauth_provider, oauth_subject_id)
);

-- Current state of each note. embedding is written only after approval --
-- see DESIGN.md section 3, unreviewed drafts never enter the searchable space.
CREATE TABLE notes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    note_type    TEXT NOT NULL CHECK (note_type IN ('claim', 'reflection', 'question')),
    content      TEXT NOT NULL,
    embedding    VECTOR(768),
    status       TEXT NOT NULL DEFAULT 'draft'
                 CHECK (status IN ('draft', 'under_review', 'approved', 'approved_merged', 'abandoned', 'merged')),
    merged_into  UUID REFERENCES notes(id),  -- set only when status='merged'; points at the surviving note
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    classify_input_tokens INT DEFAULT 0,
    classify_output_tokens INT DEFAULT 0,
    integration_input_tokens INT DEFAULT 0,
    integration_output_tokens INT DEFAULT 0
);

CREATE INDEX notes_user_id_idx ON notes (user_id);
-- ivfflat needs data present with representative distribution to tune "lists" well;
-- 100 is a reasonable starting point for a personal-scale (not internet-scale) app.
CREATE INDEX notes_embedding_idx ON notes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Append-only merge history. A merge writes a new row here and updates
-- notes.content -- it never overwrites in place. See DESIGN.md section 4.
CREATE TABLE note_versions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id        UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    version_number INT NOT NULL,
    content        TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (note_id, version_number)
);

-- One row per critique dialogue for a note.
CREATE TABLE critique_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id         UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    resolution      TEXT CHECK (resolution IN ('approved', 'abandoned')),
    override_reason TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    critic_input_tokens INT DEFAULT 0,
    critic_output_tokens INT DEFAULT 0
);

-- The actual back-and-forth transcript, one row per turn.
CREATE TABLE critique_turns (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES critique_sessions(id) ON DELETE CASCADE,
    turn_number INT NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('critic', 'user')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, turn_number)
);

-- Related-but-distinct notes -- the third option beyond merge-or-new,
-- and the actual graph structure of the knowledge base.
CREATE TABLE note_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id         UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    related_note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    link_type       TEXT NOT NULL DEFAULT 'related',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (note_id <> related_note_id)
);

-- One table for all three output types, discriminated by output_type --
-- mirrors the unified-table pattern from the prior project's contributions table.
CREATE TABLE outputs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    output_type       TEXT NOT NULL CHECK (output_type IN ('qna', 'narration', 'summary')),
    topic_query       TEXT NOT NULL,
    generated_content TEXT NOT NULL,
    pdf_path          TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    input_tokens      INT DEFAULT 0,
    output_tokens     INT DEFAULT 0,
    model_used TEXT
);

-- Provenance: which notes were retrieved to ground a given output.
CREATE TABLE output_sources (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    output_id  UUID NOT NULL REFERENCES outputs(id) ON DELETE CASCADE,
    note_id    UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE
);

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- IMPORTANT: current_setting('app.current_user_id', ...) must be set with
-- SET LOCAL inside each request's transaction, not with a plain SET on a
-- pooled connection. A pooled connection is reused across different users'
-- requests -- SET LOCAL scopes the value to the current transaction only,
-- so it can never leak into the next request that happens to reuse the
-- same connection. See DESIGN.md section 6.
-- ---------------------------------------------------------------------------

ALTER TABLE notes            ENABLE ROW LEVEL SECURITY;
ALTER TABLE note_versions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE critique_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE critique_turns   ENABLE ROW LEVEL SECURITY;
ALTER TABLE note_links       ENABLE ROW LEVEL SECURITY;
ALTER TABLE outputs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE output_sources   ENABLE ROW LEVEL SECURITY;

CREATE POLICY notes_isolation ON notes
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

CREATE POLICY note_versions_isolation ON note_versions
    USING (note_id IN (
        SELECT id FROM notes WHERE user_id = current_setting('app.current_user_id', true)::uuid
    ));

CREATE POLICY critique_sessions_isolation ON critique_sessions
    USING (note_id IN (
        SELECT id FROM notes WHERE user_id = current_setting('app.current_user_id', true)::uuid
    ));

CREATE POLICY critique_turns_isolation ON critique_turns
    USING (session_id IN (
        SELECT cs.id FROM critique_sessions cs
        JOIN notes n ON n.id = cs.note_id
        WHERE n.user_id = current_setting('app.current_user_id', true)::uuid
    ));

CREATE POLICY note_links_isolation ON note_links
    USING (note_id IN (
        SELECT id FROM notes WHERE user_id = current_setting('app.current_user_id', true)::uuid
    ));

CREATE POLICY outputs_isolation ON outputs
    USING (user_id = current_setting('app.current_user_id', true)::uuid);

CREATE POLICY output_sources_isolation ON output_sources
    USING (output_id IN (
        SELECT id FROM outputs WHERE user_id = current_setting('app.current_user_id', true)::uuid
    ));

-- ---------------------------------------------------------------------------
-- Application role
--
-- This runs as `dev`, the bootstrap user from docker-compose.yml -- and in
-- the official Postgres image, that bootstrap user is a SUPERUSER. RLS
-- policies never apply to superusers or to a table's owner, no matter how
-- they're written (FORCE ROW LEVEL SECURITY does not override this for
-- superusers specifically). Since `dev` owns every table created above, the
-- app must connect as a DIFFERENT, weaker role for RLS to actually take
-- effect. `dev` stays the schema/migration role only -- never put it in
-- DATABASE_URL for the running app again.
-- ---------------------------------------------------------------------------

CREATE ROLE app_user LOGIN PASSWORD 'app_password';

GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;