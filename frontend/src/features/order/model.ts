import type { ProductCategory, Temperature } from '../../shared/api/index.ts';

export type Settings = { largeText: boolean; largeButton: boolean; simpleScreen: boolean; stepGuide: boolean };
export const initialSettings: Settings = { largeText: false, largeButton: false, simpleScreen: false, stepGuide: false };
export const settingsStorageKey = 'kiosk-ui-settings-v1';
export const MAX_QUANTITY = 20;
export const money = (amount: number) => `${amount.toLocaleString('ko-KR')}원`;
export const categoryLabels: Record<ProductCategory, string> = { coffee: '커피', drink: '음료', food: '푸드' };
export const temperatureLabel = (temperature: Temperature) => temperature === 'iced' ? '아이스' : temperature === 'hot' ? '핫' : '기본';

const icons: Record<string, string> = {
  americano: '☕', latte: '🥛', vanilla: '☕', tea: '🍋', chocolate: '🍫', sandwich: '🥪',
  croissant: '🥐', mocha: '☕', caramel: '☕', cappuccino: '☕', matcha: '🍵',
  'earl-grey': '🫖', 'peach-tea': '🍑', bagel: '🥯', muffin: '🧁', cookie: '🍪', cake: '🍰',
};
export const productIcon = (productId: string, category: ProductCategory) => icons[productId] ?? (category === 'food' ? '🥐' : category === 'drink' ? '🥤' : '☕');

export function readSettings(raw: string | null): Settings {
  try {
    const value = JSON.parse(raw ?? 'null');
    const settings = value?.settings ?? value;
    return Object.fromEntries(Object.keys(initialSettings).map(key => [key, settings?.[key] === true])) as Settings;
  } catch { return { ...initialSettings }; }
}
