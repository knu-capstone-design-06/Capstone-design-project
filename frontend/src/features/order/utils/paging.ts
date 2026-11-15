import type { Settings } from '../model.ts';

// 목록을 쪽으로 나눕니다. 한 쪽의 줄 수는 1080 × 1920에서 잰 높이로 정한 값입니다(아래 설명). 다른 화면 크기에서는 같은 수를 쓰고 넘치는 부분은 문서 스크롤로 봅니다.
export type PagingMode = Pick<Settings, 'largeText' | 'largeButton' | 'lowScreen' | 'simpleScreen'> & Partial<Pick<Settings, 'stepGuide' | 'highContrast'>> & { voiceOn?: boolean; largeView?: boolean };

/*
 * 메뉴 한 쪽의 줄 수(큰 글씨 밖). 메뉴 화면에는 비워 두는 안내 영역이 없고, 탭 줄과 쪽 넘김 줄 사이를 상품 목록이 채웁니다.
 * 줄 수 = 그 사이에 들어가는 가장 많은 줄 수입니다. 사진 카드 한 줄은 글자 칸(기본 120, 크게 보기 211.25) + 사진 칸(주문 확인 사진
 * 160 이상) + 기본 테두리 4이고, 글자 줄은 88이며 줄 사이는 18입니다. 1080 × 1920에서 잰 목록 높이(px, 첫 줄 위 끝에서 쪽 넘김 줄
 * 18 px 위까지): 기본 1085, 큰 버튼 997, 크게 보기 898.25, 낮은 화면 662, 낮은 화면 + 큰 버튼 606, 낮은 화면 + 크게 보기 500,
 * 말로 주문 604, 말로 주문 + 큰 버튼 508, 말로 주문 + 크게 보기 366, 낮은 화면 + 말로 주문 284.
 * 한 줄도 들어가지 않으면 한 줄을 둡니다(말로 주문 + 크게 보기는 사진 150.8, 낮은 화면 + 말로 주문은 조작 영역 안에서 스크롤).
 * 각 칸은 [기본, 큰 버튼, 크게 보기]입니다. 단계별 안내를 켜면 그 줄이 담은 메뉴 바로 위에 서고 목록은 한 줄 줄어듭니다
 * (말로 주문 중에는 단계별 안내가 보이지 않습니다).
 */
const cardRows = { normal: [3, 3, 2], low: [2, 2, 1], voice: [2, 1, 1], lowVoice: [1, 1, 1] } as const;
const textRows = { normal: [10, 9, 8], low: [6, 6, 6], voice: [5, 4, 3], lowVoice: [3, 3, 3] } as const;

/** 사진 카드 한 줄의 상품 수입니다. 큰 글씨는 두 열, 그 밖은 세 열입니다(간편 화면은 글자 줄이라 1). */
export function menuColumns({ largeText, simpleScreen }: Pick<PagingMode, 'largeText' | 'simpleScreen'>): number {
  return simpleScreen ? 1 : largeText ? 2 : 3;
}

/** 메뉴 한 쪽의 상품 수입니다. */
export function menuPageSize({ largeText, largeButton, lowScreen, simpleScreen, stepGuide = false, voiceOn = false, largeView = false }: PagingMode): number {
  // 큰 글씨: 사진 카드 두 열. 사진 칸이 기본 크기의 사진(225.8) 이상인 줄 수라서 두 줄(4개), 낮은 화면·말로 주문·단계별 안내에서는 한 줄(2개)입니다.
  // 간편 화면에 큰 글씨를 더하면 작은 사진이 붙은 글자 줄 4개(낮은 화면 2개)입니다.
  if (largeText) return simpleScreen ? (lowScreen ? 2 : 4) : 2 * (lowScreen || voiceOn || stepGuide ? 1 : 2);
  const place = voiceOn ? (lowScreen ? 'lowVoice' : 'voice') : lowScreen ? 'low' : 'normal';
  const size = largeView ? 2 : largeButton ? 1 : 0;
  const rows = Math.max(1, (simpleScreen ? textRows : cardRows)[place][size] - (stepGuide && !voiceOn ? 1 : 0));
  return simpleScreen ? rows : 3 * rows;
}

/**
 * 주문 확인 한 쪽의 줄 수입니다. [쪽 넘김 없이 들어가는 줄 수, 쪽 넘김 줄이 있을 때의 줄 수]이며 1080 × 1920에서
 * 주문 확인 화면을 재어 정했습니다. 기본 크기는 다섯 줄까지입니다.
 */
export function reviewPageSize({ largeText, largeButton, lowScreen }: PagingMode, count: number): number {
  const [alone, paged] = lowScreen ? (largeText ? [1, 1] : largeButton ? [2, 2] : [3, 2]) : largeText ? [3, 2] : [5, 5];
  return count <= alone ? Math.max(1, count) : paged;
}

export function pageCount(total: number, size: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, size)));
}

/** 범위를 벗어난 쪽 번호(0부터)를 마지막 쪽 안으로 되돌립니다. */
export function clampPage(page: number, total: number, size: number): number {
  return Math.min(Math.max(0, Math.floor(page)), pageCount(total, size) - 1);
}

export function pageItems<T>(items: readonly T[], page: number, size: number): T[] {
  const start = clampPage(page, items.length, size) * size;
  return items.slice(start, start + size);
}
