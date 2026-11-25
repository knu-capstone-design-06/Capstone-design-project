import { money } from './model.ts';

/** 고객 화면의 안내 문구입니다. 서버 오류 상세는 고객에게 그대로 표시하지 않습니다. */
export const orderCopy = {
  preparing: '주문을 준비하고 있어요.',
  saving: '주문 내용을 반영하고 있어요.',
  unavailable: '주문 서비스가 아직 준비되지 않았어요. 잠시 후 다시 시도해 주세요.',
  connectionFailed: '주문을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.',
  added: '메뉴를 담았어요.',
  quantityChanged: '수량을 바꿨어요.',
  removed: '메뉴를 뺐어요.',
  voiceCartUpdated: '음성 주문을 장바구니에 반영했어요.',
  voiceCartSyncFailed: '음성 주문 결과를 불러오지 못했어요. 장바구니를 확인해 주세요.',
  ended: '이 주문을 계속할 수 없어요. 처음부터 다시 주문해 주세요.',
  failed: '주문 내용을 반영하지 못했어요. 담은 메뉴를 확인하고 다시 시도해 주세요.',
};

export const pendingCopy = {
  cart: {
    uncertain: '메뉴 변경이 반영됐는지 아직 확인하지 못했어요. 잠시 후 다시 확인해 주세요.',
    abandoned: '이전 메뉴 변경이 반영됐는지 확인하지 못했어요. 새 장바구니로 다시 시작할 수 있어요.',
    abandonWarning: '처음부터 다시 주문하면 새 장바구니로 시작해요. 이전 메뉴 변경 결과는 확인하지 못했어요.',
  },
  order: {
    uncertain: '주문이 완료됐는지 아직 확인하지 못했어요. 잠시 후 다시 확인해 주세요.',
    abandoned: '이전 주문이 완료됐는지 확인하지 못했어요. 처음부터 다시 주문할 수 있어요.',
    abandonWarning: '처음부터 다시 주문해도 이전 주문은 자동으로 취소되지 않아요.',
  },
};

const errors: Record<string, string> = {
  cart_version_conflict: '담은 메뉴가 바뀌었어요. 최신 내용을 확인해 주세요.',
  price_changed: '메뉴 가격이 바뀌었어요. 금액을 확인해 주세요.',
  product_unavailable: '선택한 메뉴가 품절됐어요. 다른 메뉴를 골라 주세요.',
  product_not_found: '선택한 메뉴를 주문할 수 없어요. 다른 메뉴를 골라 주세요.',
  cart_item_not_found: '이 메뉴는 장바구니에 없어요. 담은 메뉴를 다시 확인해 주세요.',
  quantity_limit_exceeded: '담을 수 있는 수량을 넘었어요. 수량을 줄여 주세요.',
  empty_cart: '아직 담은 메뉴가 없어요. 메뉴를 먼저 골라 주세요.',
  invalid_option: '선택한 옵션으로 주문할 수 없어요. 옵션을 다시 골라 주세요.',
};
export function orderErrorCopy(code: string, ended: boolean): string {
  return ended ? orderCopy.ended : errors[code] ?? orderCopy.failed;
}

/** [처음으로] 확인 창의 안내입니다. 어느 대답을 누르면 무엇이 지워지는지 담은 수와 금액으로 알리고, 담은 메뉴가 없으면 그 대답이 하는 일만 알립니다. */
export const restartCopy = {
  cart: (count: number, amount: number) => count > 0
    ? `'처음부터 주문하기'를 누르면 담은 메뉴 ${count}개(${money(amount)})가 모두 지워져요.`
    : "'처음부터 주문하기'를 누르면 처음 화면으로 돌아가요.",
  // 고객이 화면 도움에서 고른 설정이 켜져 있을 때만 보입니다. 키오스크가 제안해서 켠 설정은 새 주문에서 끝나므로 말하지 않습니다.
  keep: '화면 도움에서 고른 설정은 그대로예요.',
};

/** 키오스크가 먼저 띄우는 화면 지원의 문구입니다. '버튼을 크게 했어요.'는 임시로 정한 문구입니다. */
export const supportCopy = {
  // 크게 보기(큰 글씨와 큰 버튼을 함께)의 질문과 적용 알림입니다. 둘 다 임시 문구입니다.
  enlarge: { question: '글자와 버튼을 크게 해 드릴까요?', applied: '글자와 버튼을 크게 했어요.' },
  accept: '크게 하기',
  decline: '이대로 두기',
  undo: '원래대로',
};

/** 버튼 강조 힌트의 한 줄 안내입니다. 계약에 힌트를 주는 필드가 아직 없어 개발용 시험 장치로만 띄웁니다. */
export const hintCopy = {
  // 기본 크기의 옵션 시트 말풍선은 \n에서 두 줄로 나눔(white-space: pre). 줄바꿈을 따르지 않는 다른 자리에서는 빈칸 하나로 보임
  'option-add': "아래 '담기'를\n눌러 주세요",
  'cart-remove': "빼려는 메뉴 옆 '삭제'를 눌러 주세요",
};
export type HintKind = keyof typeof hintCopy;
