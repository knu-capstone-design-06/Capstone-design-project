import { useSyncExternalStore } from 'react';
import type { VoiceController, VoiceSnapshot } from './voiceController.ts';

/** VoiceController 상태를 React에서 읽습니다. 컨트롤러 생성·연결은 부르는 쪽이 합니다. */
export function useVoiceInput(controller: VoiceController): VoiceSnapshot {
  return useSyncExternalStore(controller.subscribe, controller.getSnapshot);
}
