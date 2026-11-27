import type { FeatureWindowResponse, SupportDecision } from '../../shared/api/types.ts';
import { supportCopy } from './copy.ts';
import type { Settings } from './model.ts';

export const supportSettings = {
  large_text: { key: 'largeText', question: '글씨를 크게 바꿀까요?', description: '메뉴와 안내 글씨를 크게 보여 드려요.' },
  large_button: { key: 'largeButton', question: '버튼을 크게 바꿀까요?', description: '누르는 버튼을 크게 보여 드려요.' },
  simple_screen: { key: 'simpleScreen', question: '간편한 화면으로 바꿀까요?', description: '메뉴를 간단한 목록으로 보여 드려요.' },
  step_guide: { key: 'stepGuide', question: '주문 순서를 안내해 드릴까요?', description: '현재 단계에서 할 일을 화면에 보여 드려요.' },
} as const;
export type SupportPreset = keyof typeof supportSettings;

/**
 * 시연 스위치의 결정(이름과 결정 ID가 있는 응답)으로 묻는 지원입니다. 묻는 카드(SupportConfirmSheet)와 그 규칙(띄울 수 있는 때,
 * 대답·닫음의 기억, 나타난 뒤 대답을 받지 않는 시간)은 프리셋 제안과 같습니다.
 * enlarge: 크게 보기. large_text(2-1)·large_button(4-1) 결정을 하나의 질문(copy.ts의 supportCopy.enlarge와 그 두 대답)으로 묻고,
 * 예를 누르면 두 설정(keys)을 함께 키오스크가 켠 설정으로 켭니다. 대답·닫음의 기억(memory)은 두 프리셋을 함께 덮습니다.
 * 설명 문장(낭독기용)은 디자인 명세 v11 6.4의 적용 알림 "글자와 버튼을 크게 했어요."를 바탕으로 씁니다.
 * lower_screen(1-2)·voice_order(1-1): preset none에 이 이름으로 오는 결정입니다. 질문과 대답은 디자인 명세 v11 6.2의 제안 문구입니다.
 * 화면 내리기의 예는 낮은 화면(lowScreen)을 키오스크가 켠 설정으로 켜고, 설명 문장은 명세 6.1·6.4의 적용 알림 "메뉴와 버튼을 아래로
 * 내렸어요."를 바탕으로 씁니다. 말로 주문의 예는 마이크 버튼과 같이 말로 주문을 켜고(켜는 화면 설정 없음), 설명 문장은 마이크 버튼의
 * 설명 문장(VoiceModeToggle.tsx)과 같습니다.
 */
export const askedSupports = {
  enlarge: { keys: ['largeText', 'largeButton'], memory: ['large_text', 'large_button'],
    question: supportCopy.enlarge.question, description: '글자와 버튼을 크게 보여 드려요.', accept: supportCopy.accept },
  lower_screen: { keys: ['lowScreen'], memory: ['lower_screen'],
    question: '화면을 내려 드릴까요?', description: '메뉴와 버튼을 아래로 내려 드려요.', accept: '내리기' },
  voice_order: { keys: [], memory: ['voice_order'],
    question: '말로 주문하시겠어요?', description: '켜면 한 문장을 듣고 마이크를 닫아요. 마이크 사용을 허용해 주세요.', accept: '말로 주문하기' },
} as const;
/** 이름으로 묻는 결정입니다(preset none, requires_confirmation true). */
const namedAsks: readonly string[] = ['lower_screen', 'voice_order'];
export type AskedSupport = keyof typeof askedSupports;
/** 묻는 카드 하나가 묻는 것: 팀의 프리셋 제안이나 결정으로 묻는 지원입니다. */
export type SupportAsk = SupportPreset | AskedSupport;
export const isAskedSupport = (ask: SupportAsk): ask is AskedSupport => Object.hasOwn(askedSupports, ask);
/** 예를 누르면 켜는 화면 설정입니다. */
export function askSettings(ask: SupportAsk): readonly (keyof Settings)[] {
  return isAskedSupport(ask) ? askedSupports[ask].keys : [supportSettings[ask].key];
}
/** 대답·닫음을 기억하는 이름입니다. 크게 보기는 두 프리셋을 함께 기억합니다. */
export function askMemory(ask: SupportAsk): readonly string[] {
  return isAskedSupport(ask) ? askedSupports[ask].memory : [ask];
}
/**
 * 묻지 않는 지원입니다: 이미 켜져 있음(크게 보기는 두 설정이 모두 켜져 있을 때). 말로 주문은 지금 켤 수 없을 때입니다
 * (voiceOrder false: voiceOrderAskable 참고).
 */
export function askSettled(ask: SupportAsk, settings: Settings, voiceOrder = false) {
  if (ask === 'voice_order') return !voiceOrder;
  return askSettings(ask).every(key => settings[key]);
}
/**
 * 1-1 말로 주문을 물을 수 있는 때: 메뉴 화면(말로 주문은 메뉴 화면에만 있음), 이 브라우저의 음성 인식(없으면 마이크 버튼도 두지 않음),
 * 말로 주문이 꺼져 있음.
 */
export const voiceOrderAskable = (screen: string, voice: { supported: boolean; enabled: boolean }) =>
  screen === 'menu' && voice.supported && !voice.enabled;

function validSupport(response: unknown, sessionId: string, requireAi = true): SupportDecision | null {
  if (!response || typeof response !== 'object') return null;
  const value = response as Partial<FeatureWindowResponse>;
  if (value.session_id !== sessionId || (requireAi && value.ai_available !== true) || !value.support) return null;
  const support = value.support;
  if (typeof support.requires_confirmation !== 'boolean' || !['rule_placeholder', 'jev'].includes(support.decided_by)) return null;
  return support;
}

function offeredPreset(support: SupportDecision | null, settings: Settings): SupportPreset | null {
  if (!support || !Object.hasOwn(supportSettings, support.preset)) return null;
  const preset = support.preset as SupportPreset;
  return settings[supportSettings[preset].key] ? null : preset;
}

/** 지원 여부만 읽습니다. 서버 문구나 알 수 없는 프리셋을 화면에 실행하지 않습니다. */
export function readBackendSupport(response: unknown, sessionId: string, settings: Settings): SupportPreset | null {
  return offeredPreset(validSupport(response, sessionId), settings);
}

/** 시연 스위치를 켠 backend의 결정 중 화면이 아는 것입니다. 이름과 문구 ID는 backend/app/modules/decision/rule_table.py의 것입니다. */
export const supportDecisionNames = { highlight: 'highlight_next_action', wait: 'wait_hold_timer', largeViewHelp: 'highlight_large_view_help',
  restart: 'continue_or_new_order' } as const;
export const stepsLeftMessageId = 'steps_left_notice';
export type SupportAction =
  | { kind: 'highlight'; targetId: string } // 4-2 다음에 누를 조작 강조, 2-1 화면 도움 입구(target_id support-toggle) 강조
  | { kind: 'steps_left'; stepsLeft: number } // 3-1 남은 단계 안내
  | { kind: 'wait' } // 3-2 기다림: 고객 화면에는 아무것도 띄우지 않습니다.
  | { kind: 'restart' }; // 2-2 새 손님: [처음으로]의 "처음부터 주문할까요?" 창
export type SupportDecisionRead = { name: string; decisionId: string; action: SupportAction | null };

function supportAction(support: SupportDecision): SupportAction | null {
  // 2-1 얼굴 접근의 화면 도움 강조도 4-2 강조와 같은 고리로 응답의 target_id를 가리킵니다.
  if (support.name === supportDecisionNames.highlight || support.name === supportDecisionNames.largeViewHelp) {
    return typeof support.target_id === 'string' && support.target_id ? { kind: 'highlight', targetId: support.target_id } : null;
  }
  if (support.name === supportDecisionNames.wait) return { kind: 'wait' };
  if (support.name === supportDecisionNames.restart) return { kind: 'restart' };
  // 남은 단계 안내는 문구 ID로 고릅니다. 규칙표는 남은 화면이 1개 이상일 때만 이 안내를 엽니다(rule_table.py의 steps_open).
  const stepsLeft = support.steps_left;
  if (support.message_id === stepsLeftMessageId && typeof stepsLeft === 'number' && Number.isInteger(stepsLeft) && stepsLeft >= 1) {
    return { kind: 'steps_left', stepsLeft };
  }
  return null;
}

/**
 * support의 선택 필드(name·decision_id·steps_left·target_id·message_id)를 읽습니다.
 * 이름이나 결정 ID가 없으면(시연 스위치 꺼짐) null입니다. 화면이 모르는 이름은 action이 null이라 아무것도 실행하지 않습니다.
 * ai_available은 보지 않습니다. 스위치를 켠 backend는 ai-engine 분석이 답하지 않은 창(ai_available false)에도 판단 층의 결정을
 * 싣기 때문입니다. 팀의 프리셋 읽기(readBackendSupport)는 지금처럼 ai_available true만 읽습니다.
 */
export function readSupportDecision(response: unknown, sessionId: string): SupportDecisionRead | null {
  const support = validSupport(response, sessionId, false);
  if (!support) return null;
  const { name, decision_id: decisionId } = support;
  if (typeof name !== 'string' || !name || typeof decisionId !== 'string' || !decisionId) return null;
  return { name, decisionId, action: supportAction(support) };
}

/**
 * 안내 바가 먼저 물을 프리셋입니다. 한 결정에는 한 동작만 합니다. 화면이 묻지 않고 실행하는 결정(readSupportDecision의 action이
 * 있는 응답: 강조·남은 단계 안내·기다림)은 그 경로가 맡으므로 묻지 않습니다. 예: 3-1 안내의 계약 형식인 step_guide.
 * 이름이 없는 응답(시연 스위치 꺼짐)은 readBackendSupport 그대로 묻습니다(ai_available true만 읽음).
 * 결정 ID가 있는 응답은 실행 경로(readSupportDecision)처럼 ai_available과 관계없이 읽습니다. 스위치를 켠 backend는 ai-engine 분석이
 * 답하지 않은 창에도 판단 층의 결정을 싣기 때문입니다. 그 가운데 preset large_text·large_button은 크게 보기 하나(enlarge)로 묻고,
 * preset none·requires_confirmation true에 이름 lower_screen·voice_order인 결정은 그 이름으로 묻습니다(voiceOrder: voiceOrderAskable).
 */
export function readOfferedSupport(response: unknown, sessionId: string, settings: Settings, voiceOrder = false): SupportAsk | null {
  const decision = readSupportDecision(response, sessionId);
  if (!decision) return readBackendSupport(response, sessionId, settings);
  if (decision.action) return null;
  const support = validSupport(response, sessionId, false);
  if (support?.preset === 'large_text' || support?.preset === 'large_button') return askSettled('enlarge', settings) ? null : 'enlarge';
  if (support?.preset === 'none' && support.requires_confirmation && namedAsks.includes(decision.name)) {
    const ask = decision.name as AskedSupport;
    return askSettled(ask, settings, voiceOrder) ? null : ask;
  }
  return offeredPreset(support, settings);
}

/** 안내 바에 떠 있는 묻기 카드입니다. decisionId는 카드를 연 응답의 결정 ID(시연 스위치)이고, 팀의 프리셋 제안은 null입니다. */
export type HeldAsk = { ask: SupportAsk; context: string; decisionId: string | null };
/**
 * 받아들인 응답 하나 뒤의 카드입니다(useBackendSupport가 받아들인 응답마다 부름). backend는 묻기를 붙잡는 동안 매 응답에 같은 결정 ID를
 * 싣습니다. 결정 ID로 연 카드는 이 세션의 응답이 그 결정 ID를 싣지 않으면(거둠·다른 결정·결정 없음) 내립니다(null). 결정 ID 없이 연
 * 카드(팀의 프리셋 제안), 다른 세션의 응답, 형식이 맞지 않는 응답에서는 그대로 둡니다. 버린 응답과 실패한 요청은 전송기가 넘기지 않으므로
 * 아무것도 바꾸지 않습니다.
 */
export function keepAsk(card: HeldAsk | null, response: unknown, sessionId: string): HeldAsk | null {
  if (!card || card.decisionId === null) return card;
  const support = validSupport(response, sessionId, false);
  return !support || support.decision_id === card.decisionId ? card : null;
}

/** 새 카드를 띄울 때의 화면 상태입니다(useBackendSupport). gate: 지금 새 카드를 띄울 수 있는지(화면의 조건). */
export type AskPlace = { sessionId: string; settings: Settings; voiceOrder: boolean; context: string; gate: boolean };
/**
 * 응답 하나가 안내 바에 새로 띄울 카드입니다(useBackendSupport의 receive와, 카드를 내린 같은 응답이 함께 씀). 화면이 띄울 수 없거나(gate),
 * 응답에 묻는 지원이 없거나(readOfferedSupport: 말로 주문의 조건 포함), 이 세션에서 대답했거나 이 화면 상태에서 닫은 묻기(remembered)이면
 * null입니다.
 */
export function offeredCard(response: unknown, place: AskPlace, remembered: (name: string) => boolean): HeldAsk | null {
  if (!place.gate) return null;
  const ask = readOfferedSupport(response, place.sessionId, place.settings, place.voiceOrder);
  if (!ask || askMemory(ask).some(remembered)) return null;
  return { ask, context: place.context, decisionId: readSupportDecision(response, place.sessionId)?.decisionId ?? null };
}

/**
 * 받아들인 응답 하나 뒤의 카드입니다. keepAsk가 내린 카드는 같은 응답이 실은 묻기에 바로 자리를 내줍니다(next: offeredCard를 내린 카드를
 * 뺀 화면의 조건으로 부름). 예: backend가 1-2를 거두고 1-1을 연 응답은 1-2 카드를 내리고 그 응답으로 말로 주문 카드를 띄웁니다.
 */
export function cardAfterAnswer(card: HeldAsk | null, response: unknown, sessionId: string,
  next: (response: unknown) => HeldAsk | null): HeldAsk | null {
  const kept = keepAsk(card, response, sessionId);
  return kept === null && card !== null ? next(response) : kept;
}

/**
 * 2-2 처음부터 주문 창을 기다리게 하는 카드입니다: 결정 ID 없이 연 카드(팀의 프리셋 제안)나 미리보기 제안. 결정 ID로 연 카드는 2-2 결정을
 * 실은 같은 응답이 내리므로(응답 하나는 결정 하나를 실음) 창을 기다리게 하지 않습니다.
 */
export const cardHoldsRestart = (card: HeldAsk | null, preview: boolean) => preview || (card !== null && card.decisionId === null);

/** 강조 대상(target_id)이 조작의 data-log-target과 맞는지 봅니다. '*'는 아무 글자나 맞습니다(cart:*:decrease = 모든 장바구니 줄의 빼기 버튼). */
export function matchesLogTarget(pattern: string, id: string) {
  const parts = pattern.split('*').map(part => part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return new RegExp(`^${parts.join('.*')}$`, 's').test(id);
}

export type HeldNotice = { sessionId: string; decisionId: string; stepsLeft: number };
/** 전송기(touchFeatureTransport.ts의 TransmissionState)가 이 상태이면 응답이 더 오지 않으므로 남아 있는 안내를 끝냅니다(멈춤·실패·꺼짐). */
export const answersStoppedStates: readonly string[] = ['stopped', 'error', 'idle'];

/**
 * 화면의 결정 실행(useSupportDecision)이 전송기가 받아들인 응답마다 부르는 읽기입니다. 마지막 응답의 결정(이름·ID, 개발용 상태 줄)은
 * 매번 돌려주고, 실행할 동작은 그 결정 ID를 세션에서 처음 볼 때만 돌려줍니다(강조는 유지되어 반복된 결정으로 다시 띄우지 않음).
 * 3-1 남은 단계 안내(notice)는 대기 상태의 안내라서 그 상태가 끝날 때까지 남습니다(디자인 명세 6.4: "A notice of a pending state
 * stays until the state ends"). 결정 ID를 처음 실은 응답에서 시작하고, 같은 결정 ID를 실은 응답이 오는 동안 남으며(남은 단계 수는
 * 응답을 따라감), 그 결정이 없는 응답(다른 결정이나 결정 없음)이 오면 끝나며 그 결정 ID로는 다시 띄우지 않습니다.
 * 화면·세션이 바뀌면 endNotice()로 끝냅니다(다시 띄우지 않음). 응답이 끊기면(전송 멈춤) pauseNotice()로 내리고, 뒤에 받아들인
 * 응답이 같은 결정 ID를 다시 실으면 되살립니다. backend는 그동안에도 지원을 유지하므로 한 번의 실패로 유지 기간 내내 잃지 않습니다.
 * 4-2 강조(highlight)는 띄운 결정 ID를 기억하고 받아들인 응답마다 맞춥니다: 같은 결정을 실은 응답이 오는 동안 남고, 다른 결정
 * (3-2 기다림·3-1 안내 등)이나 결정 없는 응답이 오면 내립니다(화면은 backend의 지금 결정만 보임). 고객의 다음 터치와 화면·세션
 * 변경에는 endHighlight()로 내리며, 결정 ID마다 한 번만 띄웁니다.
 * 2-2 처음부터 주문 창(restart)은 결정 ID를 처음 볼 때 쓰지 않고, 화면이 창을 연 때 restartOpened()로 씁니다. 그때까지는 그 결정을
 * 실은 응답마다 restart를 돌려줘, 다른 창이 열려 있어 열지 못한 결정을 다음 응답에서 다시 봅니다(restartPlan).
 */
export function createDecisionReader() {
  const first = createDecisionGate();
  const opened = createDecisionGate();
  let highlight: { sessionId: string; decisionId: string; targetId: string } | null = null;
  let notice: HeldNotice | null = null;
  let paused: Omit<HeldNotice, 'stepsLeft'> | null = null;
  const stepsOf = (current: SupportDecisionRead | null, sessionId: string, held: Omit<HeldNotice, 'stepsLeft'>) =>
    held.sessionId === sessionId && current?.decisionId === held.decisionId && current.action?.kind === 'steps_left' ? current.action.stepsLeft : null;
  const read = (response: unknown, sessionId: string) => {
    const current = readSupportDecision(response, sessionId);
    const restart = current?.action?.kind === 'restart' && !opened.has(sessionId, current.decisionId) ? { sessionId, decisionId: current.decisionId } : null;
    const action = current?.action && current.action.kind !== 'restart' && first(sessionId, current.decisionId) ? current.action : null;
    if (action?.kind === 'highlight') highlight = { sessionId, decisionId: current!.decisionId, targetId: action.targetId };
    else if (highlight && !(highlight.sessionId === sessionId && current?.decisionId === highlight.decisionId)) highlight = null;
    if (action?.kind === 'steps_left') { notice = { sessionId, decisionId: current!.decisionId, stepsLeft: action.stepsLeft }; paused = null; }
    else if (notice) {
      const held = stepsOf(current, sessionId, notice);
      notice = held === null ? null : held === notice.stepsLeft ? notice : { ...notice, stepsLeft: held };
    } else if (paused) {
      const held = stepsOf(current, sessionId, paused);
      notice = held === null ? null : { ...paused, stepsLeft: held };
      paused = null;
    }
    return { status: current && { name: current.name, decisionId: current.decisionId }, action, highlight, notice, restart };
  };
  return Object.assign(read, {
    restartOpened(sessionId: string, decisionId: string) { opened(sessionId, decisionId); },
    endHighlight() { highlight = null; },
    endNotice() { notice = null; paused = null; },
    pauseNotice() { if (notice) paused = { sessionId: notice.sessionId, decisionId: notice.decisionId }; notice = null; },
  });
}

/** 한 결정에는 한 번만 반응합니다. 유지되는 지원은 매 응답에 같은 decision_id로 오므로 세션마다 처음 본 ID만 true입니다. */
export function createDecisionGate() {
  let session: string | null = null;
  const seen = new Set<string>();
  const gate = (sessionId: string, decisionId: string) => {
    if (session !== sessionId) { session = sessionId; seen.clear(); }
    if (seen.has(decisionId)) return false;
    seen.add(decisionId);
    return true;
  };
  // 쓰지 않고 보기: 이 세션에서 이미 반응한 결정 ID인지
  return Object.assign(gate, { has: (sessionId: string, decisionId: string) => session === sessionId && seen.has(decisionId) });
}

/** 2-2 처음부터 주문 창을 여는 때를 정하는 화면 상태입니다(OrderPage). */
export type RestartScreen = { options: boolean; help: boolean; cart: boolean; restart: boolean; ask: boolean; restartDisabled: boolean };
/**
 * 2-2 새 손님 결정(continue_or_new_order)을 받은 화면이 할 일입니다. 처음으로 창이 이미 열려 있으면(고객이 [처음으로]를 누름) 그 결정을
 * 보인 것으로 칩니다(shown). 그래서 [계속 주문하기]로 닫은 뒤 같은 결정으로 다시 열지 않습니다. 그 결정을 부른 누름이 보통 옵션 창을
 * 열었으므로 옵션 창은 담지 않고 닫은 뒤 엽니다(close_options). 화면 도움·장바구니 창이나 제안 카드가 열려 있거나 [처음으로]를 누를 수 없는
 * 동안에는 열지 않고 같은 결정을 실은 다음 응답을 기다립니다(wait).
 */
export function restartPlan(screen: RestartScreen): 'open' | 'close_options' | 'wait' | 'shown' {
  if (screen.restart) return 'shown';
  if (screen.help || screen.cart || screen.ask || screen.restartDisabled) return 'wait';
  return screen.options ? 'close_options' : 'open';
}

/**
 * restartPlan대로 합니다(OrderPage의 openRestartForDecision): 옵션 창을 담지 않고 닫고(closeOptions), [처음으로]와 같은 처리로 창을
 * 엽니다(openRestart). 창을 열었거나 이미 열려 있었으면 true(그 결정 ID를 씀), 기다리면 false입니다.
 */
export function restartForDecision(screen: RestartScreen, { closeOptions, openRestart }: { closeOptions: () => void; openRestart: () => void }) {
  const plan = restartPlan(screen);
  if (plan === 'wait') return false;
  if (plan === 'close_options') closeOptions();
  if (plan !== 'shown') openRestart();
  return true;
}
