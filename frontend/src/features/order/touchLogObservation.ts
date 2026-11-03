import type { OrderSnapshot } from './orderController.ts';

type VoiceObservation = {
  enabled: boolean;
  microphoneActive: boolean;
  phase: string;
  autoOff?: 'silence' | 'idle' | null;
};

// 로컬 분석용 관측값입니다. 성공·불편·사용자 의도를 판정하지 않습니다.
export function captureTouchLogObservation(
  order: OrderSnapshot,
  selection: { productId: string; temperature: string | null; quantity: number } | null,
  voice: VoiceObservation,
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
    voice: {
      enabled: voice.enabled,
      microphoneActive: voice.microphoneActive,
      phase: voice.phase,
      // 사용자가 끈 경우와 자동 종료만 구분하며, 인식 문장·오류 상세는 보관하지 않습니다.
      autoOff: voice.autoOff ?? null,
    },
  };
}

export type TouchLogObservation = ReturnType<typeof captureTouchLogObservation>;
