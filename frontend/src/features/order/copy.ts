/** 고객 화면의 안내 문구입니다. 서버 오류 상세는 고객에게 그대로 표시하지 않습니다. */
export const orderCopy = {
  preparing: '주문을 준비하고 있어요.',
  saving: '주문 내용을 반영하고 있어요.',
  unavailable: '주문 서비스가 아직 준비되지 않았어요. 잠시 후 다시 시도해 주세요.',
  connectionFailed: '주문을 시작하지 못했어요. 잠시 후 다시 시도해 주세요.',
  added: '메뉴를 담았어요.',
  quantityChanged: '수량을 바꿨어요.',
  removed: '메뉴를 뺐어요.',
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
    uncertain: '샘플 주문이 완료됐는지 아직 확인하지 못했어요. 잠시 후 다시 확인해 주세요.',
    abandoned: '이전 샘플 주문이 완료됐는지 확인하지 못했어요. 처음부터 다시 주문할 수 있어요.',
    abandonWarning: '처음부터 다시 주문해도 이전 샘플 주문은 자동으로 취소되지 않아요.',
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
