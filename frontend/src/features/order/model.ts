import type { ProductCategory, Temperature } from '../../shared/api/index.ts';

export type Settings = { largeText: boolean; largeButton: boolean; simpleScreen: boolean; stepGuide: boolean; lowScreen: boolean; highContrast: boolean };
export const initialSettings: Settings = { largeText: false, largeButton: false, simpleScreen: false, stepGuide: false, lowScreen: false, highContrast: false };
export const settingsStorageKey = 'kiosk-ui-settings-v1';
export const MAX_QUANTITY = 20;
/**
 * 개발 샘플을 포함해 주문번호의 접두사를 보존합니다. 실제 주문번호로 오인하지 않도록 원래 값을 그대로 보입니다.
 */
export function orderNumberText(value: string): string {
  return value;
}

export const money = (amount: number) => `${amount.toLocaleString('ko-KR')}원`;
export const categoryLabels: Record<ProductCategory, string> = { coffee: '커피', drink: '음료', food: '푸드' };
export const temperatureLabel = (temperature: Temperature) => temperature === 'iced' ? '아이스' : temperature === 'hot' ? '핫' : '기본';
/** 고객 화면에 쓰는 온도 이름입니다(UI 가이드 p.103). 터치 로그 대상 이름은 temperatureLabel을 그대로 씁니다. */
export const temperatureText = (temperature: Temperature) => temperature === null ? '' : temperatureLabel(temperature);

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
