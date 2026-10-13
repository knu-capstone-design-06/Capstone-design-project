"""Fixed, non-personal demonstration catalog matching the frontend sample menu."""

from app.modules.ordering.schemas import Product

_ROWS = (
    ("americano", "아메리카노", "coffee", 3500, "깊고 깔끔한 에스프레소"),
    ("latte", "카페 라떼", "coffee", 4200, "부드러운 우유와 진한 커피"),
    ("vanilla", "바닐라 라떼", "coffee", 4700, "달콤한 바닐라의 여유"),
    ("tea", "레몬 티", "drink", 4000, "상큼하게 즐기는 레몬 티"),
    ("chocolate", "초콜릿 라떼", "drink", 4500, "진한 초콜릿과 부드러운 우유"),
    ("sandwich", "에그 샌드위치", "food", 5500, "든든한 달걀 샌드위치"),
    ("croissant", "버터 크루아상", "food", 3200, "겹겹이 구운 버터의 풍미"),
    ("mocha", "카페 모카", "coffee", 4800, "커피와 초콜릿의 달콤한 조화"),
    ("caramel", "카라멜 라떼", "coffee", 4800, "부드럽게 즐기는 카라멜 커피"),
    ("cappuccino", "카푸치노", "coffee", 4300, "풍성한 우유 거품과 에스프레소"),
    ("matcha", "말차 라떼", "drink", 4900, "향긋한 말차와 고소한 우유"),
    ("earl-grey", "얼그레이 티", "drink", 4000, "은은한 베르가모트 향의 홍차"),
    ("peach-tea", "복숭아 티", "drink", 4200, "달콤한 복숭아 향을 담은 티"),
    ("bagel", "플레인 베이글", "food", 3500, "담백하고 쫄깃한 베이글"),
    ("muffin", "블루베리 머핀", "food", 3800, "블루베리가 들어간 촉촉한 머핀"),
    ("cookie", "초콜릿 쿠키", "food", 2800, "초콜릿 칩이 가득한 쿠키"),
    ("cake", "딸기 케이크", "food", 6500, "딸기와 크림을 올린 조각 케이크"),
)

PRODUCTS = tuple(Product(
    product_id=product_id, name=name, category=category, description=description,
    unit_price=unit_price, available=True,
    temperatures=[] if category == "food" else ["iced", "hot"],
) for product_id, name, category, unit_price, description in _ROWS)
