import type { OrderSnapshot } from './orderController.ts';

// 로컬 분석용 관측값입니다. 성공·불편·사용자 의도를 판정하지 않습니다.
export function captureTouchLogObservation(
  order: OrderSnapshot,
  selection: { productId: string; temperature: string | null; quantity: number } | null,
  voice: { enabled: boolean; microphoneActive: boolean; phase: string },
) {
  return {
    order: {
      status: order.status,
      completed: order.order !== null,
      feedbackVisible: order.message.length > 0,
      cart: order.cart === null ? null : {
        version: order.cart.version,
        totalQuantity: order.cart.total_quantity,
        items: order.cart.items.map(item => ({
          itemId: item.item_id, productId: item.product_id, temperature: item.temperature, quantity: item.quantity,
        })),
      },
    },
    selection: selection === null ? null : { productId: selection.productId, temperature: selection.temperature, quantity: selection.quantity },
    // 인식 문장·서버 응답·오류 상세는 로그에 복사하지 않습니다.
    voice: { enabled: voice.enabled, microphoneActive: voice.microphoneActive, phase: voice.phase },
  };
}

export type TouchLogObservation = ReturnType<typeof captureTouchLogObservation>;
