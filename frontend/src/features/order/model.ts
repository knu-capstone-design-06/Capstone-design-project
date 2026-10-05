export const products = [
  { id: 'americano', name: '아메리카노', category: '커피', price: 3500, icon: '☕', description: '깊고 깔끔한 에스프레소', temperatures: ['아이스', '핫'] },
  { id: 'latte', name: '카페 라떼', category: '커피', price: 4200, icon: '🥛', description: '부드러운 우유와 진한 커피', temperatures: ['아이스', '핫'] },
  { id: 'vanilla', name: '바닐라 라떼', category: '커피', price: 4700, icon: '☕', description: '달콤한 바닐라의 여유', temperatures: ['아이스', '핫'] },
  { id: 'tea', name: '레몬 티', category: '음료', price: 4000, icon: '🍋', description: '상큼하게 즐기는 레몬 티', temperatures: ['아이스', '핫'] },
  { id: 'chocolate', name: '초콜릿 라떼', category: '음료', price: 4500, icon: '🍫', description: '진한 초콜릿과 부드러운 우유', temperatures: ['아이스', '핫'] },
  { id: 'sandwich', name: '에그 샌드위치', category: '푸드', price: 5500, icon: '🥪', description: '든든한 달걀 샌드위치', temperatures: ['기본'] },
  { id: 'croissant', name: '버터 크루아상', category: '푸드', price: 3200, icon: '🥐', description: '겹겹이 구운 버터의 풍미', temperatures: ['기본'] },
  { id: 'mocha', name: '카페 모카', category: '커피', price: 4800, icon: '☕', description: '커피와 초콜릿의 달콤한 조화', temperatures: ['아이스', '핫'] },
  { id: 'caramel', name: '카라멜 라떼', category: '커피', price: 4800, icon: '☕', description: '부드럽게 즐기는 카라멜 커피', temperatures: ['아이스', '핫'] },
  { id: 'cappuccino', name: '카푸치노', category: '커피', price: 4300, icon: '☕', description: '풍성한 우유 거품과 에스프레소', temperatures: ['아이스', '핫'] },
  { id: 'matcha', name: '말차 라떼', category: '음료', price: 4900, icon: '🍵', description: '향긋한 말차와 고소한 우유', temperatures: ['아이스', '핫'] },
  { id: 'earl-grey', name: '얼그레이 티', category: '음료', price: 4000, icon: '🫖', description: '은은한 베르가모트 향의 홍차', temperatures: ['아이스', '핫'] },
  { id: 'peach-tea', name: '복숭아 티', category: '음료', price: 4200, icon: '🍑', description: '달콤한 복숭아 향을 담은 티', temperatures: ['아이스', '핫'] },
  { id: 'bagel', name: '플레인 베이글', category: '푸드', price: 3500, icon: '🥯', description: '담백하고 쫄깃한 베이글', temperatures: ['기본'] },
  { id: 'muffin', name: '블루베리 머핀', category: '푸드', price: 3800, icon: '🧁', description: '블루베리가 들어간 촉촉한 머핀', temperatures: ['기본'] },
  { id: 'cookie', name: '초콜릿 쿠키', category: '푸드', price: 2800, icon: '🍪', description: '초콜릿 칩이 가득한 쿠키', temperatures: ['기본'] },
  { id: 'cake', name: '딸기 케이크', category: '푸드', price: 6500, icon: '🍰', description: '딸기와 크림을 올린 조각 케이크', temperatures: ['기본'] },
];
export type Product = typeof products[number];
export type CartItem = { productId: string; temperature: string; quantity: number };
export type Settings = { largeText: boolean; largeButton: boolean; simpleScreen: boolean; stepGuide: boolean };
export type OrderState = { cart: CartItem[]; settings: Settings };
export const initialState: OrderState = { cart: [], settings: { largeText: false, largeButton: false, simpleScreen: false, stepGuide: false } };
export const storageKey = 'kiosk-sample-order-v1';
export const money = (amount: number) => `${amount.toLocaleString('ko-KR')}원`;
export const total = (cart: CartItem[]) => cart.reduce((sum, item) => sum + (products.find(p => p.id === item.productId)?.price ?? 0) * item.quantity, 0);
export function addItem(cart: CartItem[], item: CartItem): CartItem[] {
  const match = cart.findIndex(row => row.productId === item.productId && row.temperature === item.temperature);
  if (match < 0) return [...cart, item];
  return cart.map((row, index) => index === match ? { ...row, quantity: Math.min(20, row.quantity + item.quantity) } : row);
}
export function readState(raw: string | null): OrderState {
  try {
    const value = JSON.parse(raw ?? 'null');
    if (!value || !Array.isArray(value.cart)) return initialState;
    const cart = value.cart.filter((row: CartItem) => {
      const product = products.find(p => p.id === row?.productId);
      return product && product.temperatures.includes(row.temperature) && Number.isInteger(row.quantity) && row.quantity > 0 && row.quantity <= 20;
    });
    const settings = Object.fromEntries(Object.keys(initialState.settings).map(key => [key, value.settings?.[key] === true])) as Settings;
    return { cart, settings };
  } catch { return initialState; }
}
