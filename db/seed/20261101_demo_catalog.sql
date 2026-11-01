-- Non-personal first-demo catalog from backend/app/modules/ordering/catalog.py.
-- Run only after 20261101092640_create_order_storage and review its prices first.
-- Existing rows are not overwritten; use a later reviewed migration for updates.

insert into kiosk.products
    (product_id, name, category, description, unit_price, available, temperatures)
values
    ('americano', '아메리카노', 'coffee', '깊고 깔끔한 에스프레소', 3500, true, array['iced', 'hot']::text[]),
    ('latte', '카페 라떼', 'coffee', '부드러운 우유와 진한 커피', 4200, true, array['iced', 'hot']::text[]),
    ('vanilla', '바닐라 라떼', 'coffee', '달콤한 바닐라의 여유', 4700, true, array['iced', 'hot']::text[]),
    ('tea', '레몬 티', 'drink', '상큼하게 즐기는 레몬 티', 4000, true, array['iced', 'hot']::text[]),
    ('chocolate', '초콜릿 라떼', 'drink', '진한 초콜릿과 부드러운 우유', 4500, true, array['iced', 'hot']::text[]),
    ('sandwich', '에그 샌드위치', 'food', '든든한 달걀 샌드위치', 5500, true, array[]::text[]),
    ('croissant', '버터 크루아상', 'food', '겹겹이 구운 버터의 풍미', 3200, true, array[]::text[]),
    ('mocha', '카페 모카', 'coffee', '커피와 초콜릿의 달콤한 조화', 4800, true, array['iced', 'hot']::text[]),
    ('caramel', '카라멜 라떼', 'coffee', '부드럽게 즐기는 카라멜 커피', 4800, true, array['iced', 'hot']::text[]),
    ('cappuccino', '카푸치노', 'coffee', '풍성한 우유 거품과 에스프레소', 4300, true, array['iced', 'hot']::text[]),
    ('matcha', '말차 라떼', 'drink', '향긋한 말차와 고소한 우유', 4900, true, array['iced', 'hot']::text[]),
    ('earl-grey', '얼그레이 티', 'drink', '은은한 베르가모트 향의 홍차', 4000, true, array['iced', 'hot']::text[]),
    ('peach-tea', '복숭아 티', 'drink', '달콤한 복숭아 향을 담은 티', 4200, true, array['iced', 'hot']::text[]),
    ('bagel', '플레인 베이글', 'food', '담백하고 쫄깃한 베이글', 3500, true, array[]::text[]),
    ('muffin', '블루베리 머핀', 'food', '블루베리가 들어간 촉촉한 머핀', 3800, true, array[]::text[]),
    ('cookie', '초콜릿 쿠키', 'food', '초콜릿 칩이 가득한 쿠키', 2800, true, array[]::text[]),
    ('cake', '딸기 케이크', 'food', '딸기와 크림을 올린 조각 케이크', 6500, true, array[]::text[])
on conflict (product_id) do nothing;
