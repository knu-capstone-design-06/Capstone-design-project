-- Initial server-owned session storage. No client or Data API access.
create schema kiosk;

revoke all on schema kiosk from public, anon, authenticated;

create table kiosk.sessions (
    session_id text primary key,
    started_at timestamptz not null default now()
);

alter table kiosk.sessions enable row level security;
revoke all on table kiosk.sessions from public, anon, authenticated;

comment on schema kiosk is 'Private backend-owned kiosk data';
comment on table kiosk.sessions is 'Session IDs and creation times only; no personal or camera data';
