-- REVIEW DRAFT ONLY. Do not run this file against Supabase.
-- PR #62 records proposals, not a settled event/support contract. In particular,
-- event kinds, response to duplicate IDs, allowed payload keys, and retention
-- periods still require frontend, AI, vision, and backend agreement.
-- Once agreed, create a NEW db/migration file and enable RLS/backend-only access.

create table kiosk.event_records (
    session_id text not null references kiosk.sessions(session_id),
    event_id text not null,
    schema_version integer not null,
    kind text not null,
    source text not null,
    occurred_at timestamptz not null,
    received_at timestamptz not null default now(),
    screen_id text,
    data jsonb not null default '{}'::jsonb,
    primary key (session_id, event_id)
);

create index event_records_session_time
    on kiosk.event_records (session_id, occurred_at);

create table kiosk.support_history (
    session_id text not null references kiosk.sessions(session_id),
    event_id text not null,
    decision_id text not null,
    phase text not null,
    preset text,
    outcome text,
    occurred_at timestamptz not null,
    received_at timestamptz not null default now(),
    data jsonb not null default '{}'::jsonb,
    primary key (session_id, event_id)
);

create index support_history_decision_time
    on kiosk.support_history (session_id, decision_id, occurred_at);

-- Before implementation: define exact kind/source/phase/outcome values and
-- event-specific data allowlists in contract/; decide the duplicate-content
-- comparison and batch rejection response; separate pilot and final-evaluation
-- data; decide retention/deletion. Never store raw images, speech, face points,
-- or raw touch coordinates in these generic JSON fields. The future migration
-- must add RLS policies and grants for kiosk_backend only.
