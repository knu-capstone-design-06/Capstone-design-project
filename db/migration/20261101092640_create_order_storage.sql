-- First-demo order storage. Apply after 20261012110139 only after a verified
-- manual backup and PR review. This does not switch the backend off memory.
-- Session end/idle policy, server events, and support history remain undecided.

create table kiosk.products (
    product_id text primary key check (length(btrim(product_id)) > 0),
    name text not null check (length(btrim(name)) > 0),
    category text not null check (category in ('coffee', 'drink', 'food')),
    description text not null,
    unit_price bigint not null check (unit_price >= 0),
    available boolean not null,
    temperatures text[] not null default array[]::text[],
    constraint products_temperatures_valid check (
        temperatures <@ array['iced', 'hot']::text[]
        and array_position(temperatures, null) is null
        and (cardinality(temperatures) < 2 or temperatures[1] <> temperatures[2])
        and (
            (category = 'food' and cardinality(temperatures) = 0)
            or (category <> 'food' and cardinality(temperatures) between 1 and 2)
        )
    )
);

create table kiosk.carts (
    session_id text primary key references kiosk.sessions(session_id) on delete cascade,
    version bigint not null default 0 check (version >= 0),
    updated_at timestamptz not null default now()
);

create table kiosk.cart_items (
    item_id text primary key check (length(btrim(item_id)) > 0),
    session_id text not null references kiosk.carts(session_id) on delete cascade,
    position integer not null check (position >= 0),
    product_id text not null references kiosk.products(product_id) on delete restrict,
    name text not null check (length(btrim(name)) > 0),
    temperature text check (temperature in ('iced', 'hot')),
    quantity integer not null check (quantity between 1 and 20),
    unit_price bigint not null check (unit_price >= 0),
    line_amount bigint generated always as (unit_price * quantity) stored,
    constraint cart_items_session_position unique (session_id, position),
    constraint cart_items_one_product_option unique nulls not distinct
        (session_id, product_id, temperature)
);

create table kiosk.orders (
    order_id text primary key check (length(btrim(order_id)) > 0),
    order_number text not null unique check (length(btrim(order_number)) > 0),
    session_id text not null unique references kiosk.sessions(session_id) on delete restrict,
    status text not null default 'simulated' check (status = 'simulated'),
    currency text not null default 'KRW' check (currency = 'KRW'),
    total_quantity integer not null check (total_quantity >= 1),
    total_amount bigint not null check (total_amount >= 0),
    created_at timestamptz not null default now()
);

create table kiosk.order_items (
    order_id text not null references kiosk.orders(order_id) on delete cascade,
    item_id text not null check (length(btrim(item_id)) > 0),
    position integer not null check (position >= 0),
    product_id text not null,
    name text not null check (length(btrim(name)) > 0),
    temperature text check (temperature in ('iced', 'hot')),
    quantity integer not null check (quantity between 1 and 20),
    unit_price bigint not null check (unit_price >= 0),
    line_amount bigint generated always as (unit_price * quantity) stored,
    primary key (order_id, item_id),
    unique (order_id, position)
);

-- The current ordering repository scopes idempotency keys to a session, across
-- cart and order operations. Store the exact successful response for replay.
create table kiosk.order_request_replays (
    session_id text not null references kiosk.sessions(session_id) on delete cascade,
    request_key text not null check (length(btrim(request_key)) > 0),
    fingerprint text not null check (length(fingerprint) > 0),
    response_kind text not null check (response_kind in ('cart', 'order')),
    response_body jsonb not null check (jsonb_typeof(response_body) = 'object'),
    recorded_at timestamptz not null default now(),
    primary key (session_id, request_key)
);

comment on table kiosk.products is 'First-demo catalog, served only by the backend';
comment on table kiosk.carts is 'One versioned cart per kiosk session; totals derive from cart_items';
comment on table kiosk.cart_items is 'Current cart lines ordered by session and position; one row per product and temperature';
comment on table kiosk.orders is 'One simulated order per session; no payment or stock change';
comment on table kiosk.order_items is 'Immutable product, option, and price snapshot at order confirmation';
comment on table kiosk.order_request_replays is 'Successful cart/order response replay by session and key';

-- kiosk is a private schema. The browser roles never receive access to these tables.
alter table kiosk.products enable row level security;
alter table kiosk.carts enable row level security;
alter table kiosk.cart_items enable row level security;
alter table kiosk.orders enable row level security;
alter table kiosk.order_items enable row level security;
alter table kiosk.order_request_replays enable row level security;

revoke all on table kiosk.products, kiosk.carts, kiosk.cart_items,
    kiosk.orders, kiosk.order_items, kiosk.order_request_replays
    from public, anon, authenticated;

grant select on table kiosk.products to kiosk_backend;
grant select, insert, update on table kiosk.carts to kiosk_backend;
grant select, insert, update, delete on table kiosk.cart_items to kiosk_backend;
grant select, insert on table kiosk.orders to kiosk_backend;
grant select, insert on table kiosk.order_items to kiosk_backend;
grant select, insert on table kiosk.order_request_replays to kiosk_backend;

create policy kiosk_backend_products_select on kiosk.products
    for select to kiosk_backend using (true);
create policy kiosk_backend_carts_select on kiosk.carts
    for select to kiosk_backend using (true);
create policy kiosk_backend_carts_insert on kiosk.carts
    for insert to kiosk_backend with check (true);
create policy kiosk_backend_carts_update on kiosk.carts
    for update to kiosk_backend using (true) with check (true);
create policy kiosk_backend_cart_items_select on kiosk.cart_items
    for select to kiosk_backend using (true);
create policy kiosk_backend_cart_items_insert on kiosk.cart_items
    for insert to kiosk_backend with check (true);
create policy kiosk_backend_cart_items_update on kiosk.cart_items
    for update to kiosk_backend using (true) with check (true);
create policy kiosk_backend_cart_items_delete on kiosk.cart_items
    for delete to kiosk_backend using (true);
create policy kiosk_backend_orders_select on kiosk.orders
    for select to kiosk_backend using (true);
create policy kiosk_backend_orders_insert on kiosk.orders
    for insert to kiosk_backend with check (true);
create policy kiosk_backend_order_items_select on kiosk.order_items
    for select to kiosk_backend using (true);
create policy kiosk_backend_order_items_insert on kiosk.order_items
    for insert to kiosk_backend with check (true);
create policy kiosk_backend_order_replays_select on kiosk.order_request_replays
    for select to kiosk_backend using (true);
create policy kiosk_backend_order_replays_insert on kiosk.order_request_replays
    for insert to kiosk_backend with check (true);
