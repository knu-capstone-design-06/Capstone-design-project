-- Already applied to the Seoul Supabase project on 2026-10-12.
-- This file records that existing migration; do not run it a second time there.
-- Configure the login password outside migrations and keep it out of Git.
create role kiosk_backend with login noinherit;

grant connect on database postgres to kiosk_backend;
grant usage on schema kiosk to kiosk_backend;
grant select, insert on table kiosk.sessions to kiosk_backend;

create policy kiosk_backend_sessions_select on kiosk.sessions
    for select to kiosk_backend using (true);
create policy kiosk_backend_sessions_insert on kiosk.sessions
    for insert to kiosk_backend with check (true);

comment on role kiosk_backend is 'Dedicated backend login; set password outside migrations before use';
