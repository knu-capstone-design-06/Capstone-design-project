import assert from 'node:assert/strict';
import test from 'node:test';
import { categoryLabels, currentSettings, initialSettings, money, orderNumberText, readSettings, temperatureLabel, temperatureText, withAutomatic, withoutAutomatic } from './model.ts';
import { ApiError } from '../../shared/api/client.ts';
import { OrderController } from './orderController.ts';
import { OrderResponseError, readOrderResponse } from './orderResponse.ts';
import { clampPage, menuColumns, menuPageSize, pageCount, pageItems, reviewPageSize } from './utils/paging.ts';
import { askedSupports, askMemory, askSettings, askSettled, cardAfterAnswer, cardHoldsRestart, createDecisionGate, createDecisionReader, keepAsk, matchesLogTarget, offeredCard, readBackendSupport, readOfferedSupport, readSupportDecision, restartForDecision, restartPlan, supportSettings, voiceOrderAskable } from './backendSupport.ts';
import { stepsLeftCopy, supportCopy } from './copy.ts';

test('서버의 네 가지 제안은 각각의 설정에 연결하고 켜진 설정·잘못된 응답은 무시한다', () => {
  const response = preset => ({ session_id: 'session', ai_available: true, support: { preset, requires_confirmation: true, decided_by: 'jev' } });
  for (const [preset, { key }] of Object.entries(supportSettings)) {
    assert.equal(readBackendSupport(response(preset), 'session', initialSettings), preset);
    assert.equal(readBackendSupport(response(preset), 'session', { ...initialSettings, [key]: true }), null);
    assert.equal(readBackendSupport({ ...response(preset), support: { ...response(preset).support, requires_confirmation: false } }, 'session', initialSettings), preset);
  }
  for (const value of [null, {}, response('none'), response('voice_guide'), response('__proto__'),
    { ...response('large_text'), ai_available: false }, { ...response('large_text'), session_id: 'old' },
    { ...response('large_text'), support: { preset: 'large_text', requires_confirmation: 'true', decided_by: 'jev' } },
    { ...response('large_text'), support: { preset: 'large_text', requires_confirmation: true, decided_by: 'unknown' } }]) {
    assert.equal(readBackendSupport(value, 'session', initialSettings), null);
  }
});

// backend 시연 스위치(DECISION_SEND_SUPPORT)를 켠 /features 응답의 support 예: 4-2 강조, 3-1 남은 단계 안내, 3-2 기다림
const switched = (support, extra = {}) => ({ session_id: 'session', ai_available: true, states: null, model_version: 'dummy-0.1',
  support: { preset: 'none', requires_confirmation: false, decided_by: 'rule_placeholder', ...support }, ...extra });
const highlight = switched({ name: 'highlight_next_action', decision_id: 'd0001', steps_left: 2, target_id: 'cart-add' });
const stepsNotice = switched({ preset: 'step_guide', name: 'remaining_steps_notice', decision_id: 'd0001', steps_left: 2, target_id: 'cart_progress', message_id: 'steps_left_notice' });
const wait = switched({ name: 'wait_hold_timer', decision_id: 'd0003' });

test('시연 스위치 응답의 이름·결정 ID와 강조·남은 단계 안내·기다림을 읽는다', () => {
  assert.deepEqual(readSupportDecision(highlight, 'session'), { name: 'highlight_next_action', decisionId: 'd0001', action: { kind: 'highlight', targetId: 'cart-add' } });
  assert.deepEqual(readSupportDecision(switched({ ...highlight.support, target_id: 'cart:*:decrease' }), 'session').action, { kind: 'highlight', targetId: 'cart:*:decrease' });
  assert.deepEqual(readSupportDecision(stepsNotice, 'session'), { name: 'remaining_steps_notice', decisionId: 'd0001', action: { kind: 'steps_left', stepsLeft: 2 } });
  assert.deepEqual(readSupportDecision(wait, 'session'), { name: 'wait_hold_timer', decisionId: 'd0003', action: { kind: 'wait' } });
  // 네 프리셋은 기존처럼 먼저 묻는 경로로 갑니다. 강조·기다림의 none은 제안하지 않습니다.
  assert.equal(readBackendSupport(stepsNotice, 'session', initialSettings), 'step_guide');
  assert.equal(readBackendSupport(highlight, 'session', initialSettings), null);
  assert.equal(readBackendSupport(wait, 'session', initialSettings), null);
});

test('시연 스위치를 끈 응답·잘못된 응답에서는 결정을 읽지 않고, 모르는 이름은 실행하지 않는다', () => {
  // 스위치를 끈 backend의 응답(선택 필드 없음)은 지금과 같이 프리셋만 읽습니다.
  for (const preset of ['none', 'large_text']) assert.equal(readSupportDecision(switched({ preset }), 'session'), null);
  for (const value of [null, {}, { ...highlight, session_id: 'old' }, { ...highlight, ai_available: false, session_id: 'old' },
    switched({ ...highlight.support, decision_id: undefined }), switched({ ...highlight.support, decision_id: '' }),
    switched({ ...highlight.support, decision_id: 1 }), switched({ ...highlight.support, name: undefined }),
    switched({ ...highlight.support, decided_by: 'unknown' }), switched({ ...highlight.support, requires_confirmation: 'false' })]) {
    assert.equal(readSupportDecision(value, 'session'), null);
  }
  // 모르는 이름·문구 ID와 실행할 값이 없는 결정은 이름만 읽고 아무것도 실행하지 않습니다.
  for (const support of [{ name: 'delay_responsibility_notice', message_id: 'delay_responsibility_notice', steps_left: 2 },
    { name: 'large_button', preset: 'large_button', requires_confirmation: true }, { name: 'some_new_support' },
    { name: 'highlight_next_action' }, { name: 'highlight_next_action', target_id: '' },
    { name: 'remaining_steps_notice', message_id: 'steps_left_notice' }, { name: 'remaining_steps_notice', message_id: 'steps_left_notice', steps_left: 0 },
    { name: 'remaining_steps_notice', message_id: 'steps_left_notice', steps_left: 1.5 }, { name: 'remaining_steps_notice', message_id: 'steps_left_notice', steps_left: '2' }]) {
    const read = readSupportDecision(switched({ ...support, decision_id: 'd0009' }), 'session');
    assert.equal(read.name, support.name);
    assert.equal(read.action, null, JSON.stringify(support));
  }
});

test('ai-engine 분석이 답하지 않은 창(ai_available false)의 결정도 실행하고, 팀의 프리셋 읽기는 지금처럼 버린다', () => {
  // 스위치를 켠 backend는 ai_available false에도 결정과 실행 필드를 싣습니다(states·model_version은 null).
  const unanalysed = value => ({ ...value, ai_available: false, states: null, model_version: null });
  assert.deepEqual(readSupportDecision(unanalysed(highlight), 'session'), readSupportDecision(highlight, 'session'));
  assert.deepEqual(readSupportDecision(unanalysed(stepsNotice), 'session').action, { kind: 'steps_left', stepsLeft: 2 });
  assert.deepEqual(readSupportDecision(unanalysed(wait), 'session').action, { kind: 'wait' });
  // 세션이 다르거나 이름·결정 ID가 없으면 ai_available과 관계없이 읽지 않습니다.
  for (const value of [{ ...unanalysed(highlight), session_id: 'old' }, unanalysed(switched({ preset: 'none' })),
    unanalysed(switched({ ...highlight.support, decision_id: undefined }))]) {
    assert.equal(readSupportDecision(value, 'session'), null);
  }
  // 팀의 프리셋 읽기(readBackendSupport)는 ai_available true만 읽습니다(바뀌지 않음).
  const bigButton = switched({ preset: 'large_button', requires_confirmation: true, name: 'large_button', decision_id: 'd0002' });
  for (const value of [unanalysed(stepsNotice), unanalysed(bigButton)]) {
    assert.equal(readBackendSupport(value, 'session', initialSettings), null);
  }
  assert.equal(readOfferedSupport(unanalysed(stepsNotice), 'session', initialSettings), null, '실행하는 결정은 묻지 않음');
});

test('결정 ID가 있는 응답은 묻는 지원도 ai_available과 관계없이 읽고, 결정 ID가 없는 응답(스위치 꺼짐)은 지금처럼 ai_available true만 읽는다', () => {
  const unanalysed = value => ({ ...value, ai_available: false, states: null, model_version: null });
  const simple = switched({ preset: 'simple_screen', requires_confirmation: true, name: 'simple_screen', decision_id: 'd0007' });
  assert.equal(readOfferedSupport(unanalysed(simple), 'session', initialSettings), 'simple_screen');
  assert.equal(readOfferedSupport(simple, 'session', initialSettings), 'simple_screen');
  assert.equal(readOfferedSupport(unanalysed(simple), 'session', { ...initialSettings, simpleScreen: true }), null, '이미 켠 설정');
  // 결정 ID가 없으면(스위치 꺼짐) ai_available false는 지금처럼 버립니다.
  const off = { session_id: 'session', ai_available: false, support: { preset: 'simple_screen', requires_confirmation: true, decided_by: 'rule_placeholder' } };
  assert.equal(readOfferedSupport(off, 'session', initialSettings), null);
  assert.equal(readOfferedSupport({ ...off, ai_available: true }, 'session', initialSettings), 'simple_screen');
  // 세션이 다르거나 형식이 틀리면 결정 ID가 있어도 읽지 않습니다.
  for (const value of [{ ...unanalysed(simple), session_id: 'old' }, unanalysed(switched({ ...simple.support, decided_by: 'unknown' }))]) {
    assert.equal(readOfferedSupport(value, 'session', initialSettings), null);
  }
});

test('한 결정에는 한 동작: 화면이 실행하는 결정(안내·기다림·강조)은 안내 바에서 묻지 않고, 4-1 크게 보기는 묻는다', () => {
  // 3-1 안내의 계약 형식은 step_guide지만, 안내 바는 묻지 않습니다(남은 단계 안내만).
  assert.equal(readBackendSupport(stepsNotice, 'session', initialSettings), 'step_guide', '팀의 프리셋 읽기는 그대로');
  for (const value of [stepsNotice, wait, highlight, switched({ ...highlight.support, target_id: 'cart:*:decrease' })]) {
    assert.equal(readOfferedSupport(value, 'session', initialSettings), null, value.support.name);
  }
  // 화면이 실행하지 않는 결정(4-1, large_button)은 이름이 있어도 먼저 묻습니다: 크게 보기 하나로 묻습니다.
  const bigButton = switched({ preset: 'large_button', requires_confirmation: true, name: 'large_button', decision_id: 'd0002' });
  assert.equal(readSupportDecision(bigButton, 'session').action, null);
  assert.equal(readOfferedSupport(bigButton, 'session', initialSettings), 'enlarge');
  assert.equal(readOfferedSupport(bigButton, 'session', { ...initialSettings, largeButton: true, largeText: true }), null, '두 설정이 이미 켜짐');
});

test('크게 보기: large_text(2-1)와 large_button(4-1) 결정은 하나의 질문으로 묻고, 예는 두 설정을 켜며, 기억은 두 프리셋을 함께 덮는다', () => {
  const zoom = switched({ preset: 'large_text', requires_confirmation: true, name: 'large_text', decision_id: 'd0011' });
  const fixes = switched({ preset: 'large_button', requires_confirmation: true, name: 'large_button', decision_id: 'd0012' });
  for (const value of [zoom, fixes, { ...zoom, ai_available: false }]) {
    assert.equal(readOfferedSupport(value, 'session', initialSettings), 'enlarge');
    // 한 설정만 켜져 있으면 여전히 묻고(예를 누르면 둘 다 켬), 둘 다 켜져 있으면 묻지 않습니다.
    assert.equal(readOfferedSupport(value, 'session', { ...initialSettings, largeText: true }), 'enlarge');
    assert.equal(readOfferedSupport(value, 'session', { ...initialSettings, largeButton: true }), 'enlarge');
    assert.equal(readOfferedSupport(value, 'session', { ...initialSettings, largeText: true, largeButton: true }), null);
  }
  // 질문과 대답은 화면에 있던 크게 보기의 글(copy.ts의 supportCopy.enlarge와 두 대답)입니다.
  assert.equal(askedSupports.enlarge.question, supportCopy.enlarge.question);
  assert.equal(askedSupports.enlarge.question, '글자와 버튼을 크게 해 드릴까요?');
  assert.equal(askedSupports.enlarge.accept, '크게 하기');
  assert.equal(supportCopy.decline, '이대로 두기');
  // 예를 누르면 켜는 설정과 대답·닫음의 기억(useBackendSupport의 answer·dismiss가 쓰는 값)
  assert.deepEqual(askSettings('enlarge'), ['largeText', 'largeButton']);
  assert.deepEqual(askMemory('enlarge'), ['large_text', 'large_button']);
  assert.equal(askSettled('enlarge', { ...initialSettings, largeText: true }), false);
  assert.equal(askSettled('enlarge', { ...initialSettings, largeText: true, largeButton: true }), true);
  // useBackendSupport처럼: 2-1의 질문에 대답하면 같은 세션의 4-1 질문도 다시 띄우지 않습니다(반대도 같음).
  for (const [first, later] of [[zoom, fixes], [fixes, zoom]]) {
    const answered = new Set(askMemory(readOfferedSupport(first, 'session', initialSettings)));
    const next = readOfferedSupport(later, 'session', initialSettings);
    assert.equal(askMemory(next).some(name => answered.has(name)), true);
  }
  // 결정 ID가 없는 응답(스위치 꺼짐)은 지금처럼 두 프리셋을 각각의 질문으로 묻고 그 설정 하나만 켭니다.
  for (const [preset, key] of [['large_text', 'largeText'], ['large_button', 'largeButton']]) {
    const off = { session_id: 'session', ai_available: true, support: { preset, requires_confirmation: true, decided_by: 'rule_placeholder' } };
    assert.equal(readOfferedSupport(off, 'session', initialSettings), preset);
    assert.deepEqual(askSettings(preset), [key]);
    assert.deepEqual(askMemory(preset), [preset]);
  }
});

test('시연 스위치를 끈 응답(이름 없음)은 안내 바에서 지금과 같이 읽는다', () => {
  const response = (preset, requires_confirmation) => ({ session_id: 'session', ai_available: true, support: { preset, requires_confirmation, decided_by: 'rule_placeholder' } });
  for (const preset of ['none', ...Object.keys(supportSettings), 'voice_guide']) {
    for (const confirm of [true, false]) {
      for (const settings of [initialSettings, { ...initialSettings, largeText: true, largeButton: true, simpleScreen: true, stepGuide: true }]) {
        const value = response(preset, confirm);
        assert.equal(readOfferedSupport(value, 'session', settings), readBackendSupport(value, 'session', settings), `${preset} ${confirm}`);
      }
    }
  }
  for (const value of [null, {}, { ...response('large_text', true), ai_available: false }, { ...response('large_text', true), session_id: 'old' }]) {
    assert.equal(readOfferedSupport(value, 'session', initialSettings), null);
  }
});

test('1-2 화면 내리기와 1-1 말로 주문은 이름으로 묻고, 이미 켜져 있으면(말로 주문은 메뉴 화면 밖·음성 인식 없음도) 묻지 않는다', () => {
  const named = (name, extra = {}) => switched({ preset: 'none', requires_confirmation: true, name, decision_id: 'd0021', ...extra });
  // 화면 내리기: 질문·대답은 디자인 명세 v11 6.2, 예는 낮은 화면을 켭니다.
  assert.equal(readOfferedSupport(named('lower_screen'), 'session', initialSettings), 'lower_screen');
  assert.equal(readOfferedSupport({ ...named('lower_screen'), ai_available: false }, 'session', initialSettings), 'lower_screen', 'ai_available과 관계없음');
  assert.equal(readOfferedSupport(named('lower_screen'), 'session', { ...initialSettings, lowScreen: true }), null, '이미 낮은 화면');
  assert.deepEqual(askSettings('lower_screen'), ['lowScreen']);
  assert.deepEqual([askedSupports.lower_screen.question, askedSupports.lower_screen.accept], ['화면을 내려 드릴까요?', '내리기']);
  // 말로 주문: 물을 수 있는 때(voiceOrderAskable)에만 묻고, 예는 켜는 화면 설정 없이 말로 주문을 켭니다(useBackendSupport의 onVoiceOrder).
  const voice = named('voice_order');
  assert.equal(readOfferedSupport(voice, 'session', initialSettings, true), 'voice_order');
  assert.equal(readOfferedSupport(voice, 'session', initialSettings, false), null);
  assert.equal(readOfferedSupport(voice, 'session', initialSettings), null, '물을 수 있는지 모르면 묻지 않음');
  assert.deepEqual(askSettings('voice_order'), []);
  assert.deepEqual([askedSupports.voice_order.question, askedSupports.voice_order.accept], ['말로 주문하시겠어요?', '말로 주문하기']);
  assert.equal(voiceOrderAskable('menu', { supported: true, enabled: false }), true);
  assert.equal(voiceOrderAskable('review', { supported: true, enabled: false }), false, '메뉴 화면 밖');
  assert.equal(voiceOrderAskable('menu', { supported: true, enabled: true }), false, '이미 켜짐');
  assert.equal(voiceOrderAskable('menu', { supported: false, enabled: false }), false, '음성 인식 없음');
  assert.equal(askSettled('voice_order', initialSettings, false), true);
  assert.equal(askSettled('voice_order', initialSettings, true), false);
  // 대답·닫음의 기억은 지원마다 따로입니다.
  assert.deepEqual([askMemory('lower_screen'), askMemory('voice_order')], [['lower_screen'], ['voice_order']]);
  // 형식이 다르면 묻지 않습니다: 확인이 필요 없다는 결정, preset이 none이 아닌 결정, 모르는 이름
  for (const value of [named('lower_screen', { requires_confirmation: false }), named('voice_order', { requires_confirmation: false }),
    named('continue_or_new_order'), named('some_new_support')]) {
    assert.equal(readOfferedSupport(value, 'session', initialSettings, true), null, JSON.stringify(value.support));
  }
  assert.equal(readOfferedSupport(named('lower_screen', { preset: 'simple_screen' }), 'session', initialSettings), 'simple_screen', '프리셋이 있으면 그 프리셋');
});

test('결정 ID로 연 묻기 카드는 이 세션의 응답이 그 결정 ID를 싣지 않으면 내리고, 결정 ID 없이 연 카드는 그대로 둔다', () => {
  const lower = switched({ preset: 'none', requires_confirmation: true, name: 'lower_screen', decision_id: 'd0021' });
  const card = { ask: 'lower_screen', context: 'menu', decisionId: 'd0021' };
  assert.equal(keepAsk(card, lower, 'session'), card, 'backend가 붙잡은 동안 같은 결정 ID');
  assert.equal(keepAsk(card, switched({ preset: 'none', requires_confirmation: true, name: 'voice_order', decision_id: 'd0022' }), 'session'), null, '다른 결정');
  assert.equal(keepAsk(card, switched({}), 'session'), null, '결정 없음(backend가 거둠)');
  assert.equal(keepAsk(card, { ...switched({}), ai_available: false }, 'session'), null, 'ai_available false여도 결정 응답');
  assert.equal(keepAsk(card, { ...switched({}), session_id: 'old' }, 'session'), card, '다른 세션의 응답');
  for (const value of [null, {}, { session_id: 'session' }, { ...lower, support: { ...lower.support, decided_by: 'x' } }]) {
    assert.equal(keepAsk(card, value, 'session'), card, `형식이 맞지 않는 응답: ${JSON.stringify(value)}`);
  }
  const nameless = { ask: 'large_text', context: 'menu', decisionId: null };
  assert.equal(keepAsk(nameless, switched({}), 'session'), nameless, '팀의 프리셋 제안은 지금처럼');
  assert.equal(keepAsk(null, lower, 'session'), null);
});

test('카드를 내린 응답이 실은 묻기는 새 카드와 같은 확인을 거쳐 그 응답에 뜬다', () => {
  const named = (name, decision_id) => switched({ preset: 'none', requires_confirmation: true, name, decision_id });
  const place = (gate, voiceOrder = true) => ({ sessionId: 'session', settings: initialSettings, voiceOrder, context: 'menu', gate });
  const none = () => false;
  const never = () => { throw new Error('the next ask is read only when the card leaves'); };
  const voice = named('voice_order', 'd0022');
  // offeredCard: receive가 새 카드를 띄울 때의 확인(화면의 조건, 말로 주문의 조건, 대답·닫음의 기억)
  assert.deepEqual(offeredCard(voice, place(true), none), { ask: 'voice_order', context: 'menu', decisionId: 'd0022' });
  assert.equal(offeredCard(voice, place(false), none), null, '화면이 지금 띄울 수 없음');
  assert.equal(offeredCard(voice, place(true, false), none), null, '말로 주문을 물을 수 없음');
  assert.equal(offeredCard(voice, place(true), name => name === 'voice_order'), null, '이미 대답했거나 닫음');
  assert.deepEqual(offeredCard(switched({ preset: 'large_text', requires_confirmation: true, decided_by: 'jev' }), place(true), none),
    { ask: 'large_text', context: 'menu', decisionId: null }, '팀의 프리셋 제안');
  // cardAfterAnswer: 내린 카드는 같은 응답의 묻기에 바로 자리를 내줌
  const lower = { ask: 'lower_screen', context: 'menu', decisionId: 'd0021' };
  assert.deepEqual(cardAfterAnswer(lower, voice, 'session', r => offeredCard(r, place(true), none)),
    { ask: 'voice_order', context: 'menu', decisionId: 'd0022' }, '1-2 카드를 내린 응답에 1-1 카드');
  assert.equal(cardAfterAnswer(lower, voice, 'session', r => offeredCard(r, place(false), none)), null, '화면이 막으면 내리기만');
  assert.equal(cardAfterAnswer(lower, switched({}), 'session', r => offeredCard(r, place(true), none)), null, '결정 없는 응답');
  assert.equal(cardAfterAnswer(lower, named('lower_screen', 'd0021'), 'session', never), lower, '붙잡힌 묻기는 그대로');
  const nameless = { ask: 'large_text', context: 'menu', decisionId: null };
  assert.equal(cardAfterAnswer(nameless, voice, 'session', never), nameless, '결정 ID 없는 카드는 그대로');
  assert.equal(cardAfterAnswer(null, voice, 'session', never), null, '카드가 없으면 receive가 맡음');
});

test('2-2 창은 결정 ID 없이 연 카드나 미리보기 제안만 기다리게 하고, 결정 ID로 연 카드는 기다리게 하지 않는다', () => {
  assert.equal(cardHoldsRestart({ ask: 'lower_screen', context: 'menu', decisionId: 'd0021' }, false), false, '결정 ID로 연 카드는 같은 응답이 내림');
  assert.equal(cardHoldsRestart({ ask: 'large_text', context: 'menu', decisionId: null }, false), true, '팀의 프리셋 제안');
  assert.equal(cardHoldsRestart(null, true), true, '미리보기 제안');
  assert.equal(cardHoldsRestart(null, false), false);
});

test('2-1 화면 도움 강조(highlight_large_view_help)는 4-2 강조와 같은 고리로 응답의 target_id를 가리키고, 결정 ID마다 한 번만 띄운다', () => {
  const help = (decision_id, extra = {}) => switched({ name: 'highlight_large_view_help', decision_id, target_id: 'support-toggle', ...extra });
  assert.deepEqual(readSupportDecision(help('d0031'), 'session'), { name: 'highlight_large_view_help', decisionId: 'd0031', action: { kind: 'highlight', targetId: 'support-toggle' } });
  assert.deepEqual(readSupportDecision({ ...help('d0031'), ai_available: false }, 'session').action, { kind: 'highlight', targetId: 'support-toggle' });
  assert.equal(readSupportDecision(help('d0031', { target_id: undefined }), 'session').action, null, '대상이 없으면 아무것도 하지 않음');
  assert.equal(readOfferedSupport(help('d0031'), 'session', initialSettings), null, '안내 바에서 묻지 않음');
  assert.equal(matchesLogTarget('support-toggle', 'support-toggle'), true);
  const read = createDecisionReader();
  assert.equal(read(help('d0031'), 'session').action?.kind, 'highlight');
  const kept = read(help('d0031'), 'session');
  assert.equal(kept.action, null, '유지되어 반복된 결정은 다시 실행하지 않음');
  assert.deepEqual(kept.highlight, { sessionId: 'session', decisionId: 'd0031', targetId: 'support-toggle' }, '고리는 남음');
  read.endHighlight(); // 고객의 다음 터치
  assert.equal(read(help('d0031'), 'session').highlight, null);
  // 크게 보기 질문으로 바뀌면(묻는 지원이 조용한 강조를 대신함) 고리를 내립니다.
  read(help('d0032'), 'session');
  assert.equal(read(switched({ preset: 'large_text', requires_confirmation: true, name: 'large_text', decision_id: 'd0033' }), 'session').highlight, null);
});

test('2-2 새 손님(continue_or_new_order)은 처음부터 주문 창을 열고, 결정 ID는 창을 연 때만 쓴다', () => {
  const swap = decision_id => switched({ preset: 'none', requires_confirmation: true, name: 'continue_or_new_order', decision_id, steps_left: 2 });
  assert.deepEqual(readSupportDecision(swap('d0041'), 'session').action, { kind: 'restart' });
  assert.deepEqual(readSupportDecision({ ...swap('d0041'), ai_available: false }, 'session').action, { kind: 'restart' });
  assert.equal(readOfferedSupport(swap('d0041'), 'session', initialSettings, true), null, '안내 바에서 묻지 않음');
  const read = createDecisionReader();
  // 창을 열지 못한 동안(다른 창이 열림)에는 같은 결정을 실은 응답마다 다시 돌려줍니다.
  assert.deepEqual(read(swap('d0041'), 'session').restart, { sessionId: 'session', decisionId: 'd0041' });
  assert.deepEqual(read(swap('d0041'), 'session').restart, { sessionId: 'session', decisionId: 'd0041' });
  assert.equal(read(swap('d0041'), 'session').action, null, '첫 응답에 쓰지 않음(실행은 restart로)');
  read.restartOpened('session', 'd0041'); // 화면이 창을 엶
  assert.equal(read(swap('d0041'), 'session').restart, null, '연 결정 ID로는 다시 열지 않음');
  assert.deepEqual(read(swap('d0042'), 'session').restart, { sessionId: 'session', decisionId: 'd0042' }, '새 사건의 결정');
  assert.equal(read(switched({ preset: 'none' }), 'session').restart, null, '결정 없는 응답');
  assert.deepEqual(read({ ...swap('d0041'), session_id: 'next' }, 'next').restart, { sessionId: 'next', decisionId: 'd0041' }, '새 세션은 처음부터');
  // 다른 결정의 첫 실행(강조)은 이 기억과 따로입니다.
  const ring = switched({ name: 'highlight_next_action', decision_id: 'd0043', target_id: 'cart-add' });
  assert.equal(read(ring, 'session').action?.kind, 'highlight');
});

test('2-2 창을 여는 때: 옵션 창은 담지 않고 닫은 뒤 열고, 다른 창·제안 카드나 [처음으로]를 누를 수 없는 동안은 기다리며, 이미 열린 처음으로 창은 연 것으로 친다', () => {
  const closed = { options: false, help: false, cart: false, restart: false, ask: false, restartDisabled: false };
  assert.equal(restartPlan(closed), 'open');
  assert.equal(restartPlan({ ...closed, options: true }), 'close_options');
  for (const key of ['help', 'cart', 'ask', 'restartDisabled']) {
    assert.equal(restartPlan({ ...closed, [key]: true }), 'wait', key);
    assert.equal(restartPlan({ ...closed, options: true, [key]: true }), 'wait', `options + ${key}`);
    assert.equal(restartPlan({ ...closed, restart: true, [key]: true }), 'shown', `restart + ${key}`);
  }
  assert.equal(restartPlan({ ...closed, restart: true }), 'shown');
  // restartForDecision: 그 계획대로 두 처리를 부르고, 결정 ID를 쓸지(true) 돌려줍니다.
  const run = screen => { const done = []; const used = restartForDecision(screen, { closeOptions: () => done.push('close_options'), openRestart: () => done.push('open') }); return [used, done]; };
  assert.deepEqual(run(closed), [true, ['open']]);
  assert.deepEqual(run({ ...closed, options: true }), [true, ['close_options', 'open']]);
  assert.deepEqual(run({ ...closed, help: true }), [false, []]);
  assert.deepEqual(run({ ...closed, restart: true }), [true, []], '이미 열린 창: 다시 열지 않고 결정 ID를 씀');
});

test('[화면 위로 올리기]는 키오스크가 켠 낮은 화면(1-2 [내리기])도 끄고, 키오스크가 켠 다른 설정은 남긴다', () => {
  const none = { sessionId: '', values: {} };
  // 1-2 [내리기]와 크게 보기의 예처럼 키오스크가 켠 설정(OrderPage의 onApply)
  const raised = withAutomatic(withAutomatic(none, 'session', 'lowScreen'), 'session', 'largeText');
  assert.equal(currentSettings(initialSettings, raised, 'session').lowScreen, true);
  // 고객 설정만 끄던 예전 처리는 키오스크가 켠 값이 덮어 화면이 올라가지 않았습니다.
  assert.equal(currentSettings({ ...initialSettings, lowScreen: false }, raised, 'session').lowScreen, true);
  // [화면 위로 올리기]: 고객 설정의 lowScreen을 끄고 키오스크가 켠 lowScreen을 뺍니다.
  const after = currentSettings({ ...initialSettings, lowScreen: false }, withoutAutomatic(raised, ['lowScreen']), 'session');
  assert.equal(after.lowScreen, false);
  assert.equal(after.largeText, true, '키오스크가 켠 다른 설정은 남음');
  // 고객이 직접 켠 낮은 화면도 지금처럼 끕니다.
  assert.equal(currentSettings({ ...initialSettings, lowScreen: false }, withoutAutomatic(none, ['lowScreen']), 'session').lowScreen, false);
  // 키오스크가 켠 설정은 그 세션에만 덮이고, 새 세션에서 더하면 이전 세션의 값은 버립니다.
  assert.equal(currentSettings(initialSettings, raised, 'next').lowScreen, false);
  assert.deepEqual(withAutomatic(raised, 'next', 'largeButton'), { sessionId: 'next', values: { largeButton: true } });
});

test('강조 대상은 data-log-target과 같거나 *가 아무 글자에 맞는 조작이다', () => {
  assert.equal(matchesLogTarget('cart-add', 'cart-add'), true);
  for (const id of ['cart-add:x', 'xcart-add', 'cart-sheet-open']) assert.equal(matchesLogTarget('cart-add', id), false);
  for (const id of ['cart:americano:아이스:decrease', 'cart:cookie:기본:decrease']) assert.equal(matchesLogTarget('cart:*:decrease', id), true);
  for (const id of ['cart:americano:아이스:increase', 'cart:americano:아이스:remove', 'review-back', 'cart:decrease']) {
    assert.equal(matchesLogTarget('cart:*:decrease', id), false, id);
  }
  assert.equal(matchesLogTarget('menu-page:(next)', 'menu-page:(next)'), true, '정규식 기호는 글자 그대로');
  assert.equal(matchesLogTarget('menu-page:.', 'menu-page:x'), false);
});

test('남은 단계 안내는 응답의 steps_left를 디자인 명세의 문구에 넣는다', () => {
  assert.equal(stepsLeftCopy(readSupportDecision(stepsNotice, 'session').action.stepsLeft), '앞으로 2단계 남았어요');
  assert.equal(stepsLeftCopy(1), '앞으로 1단계 남았어요');
});

test('3-1 남은 단계 안내는 같은 결정 ID를 실은 응답이 오는 동안 남고, 그 결정이 없는 응답이나 끝내기에 끝난다', () => {
  const read = createDecisionReader();
  const notice = (decision_id, steps_left) => switched({ ...stepsNotice.support, decision_id, steps_left });
  const held = response => read(response, 'session').notice;
  assert.deepEqual(held(notice('d0001', 2)), { sessionId: 'session', decisionId: 'd0001', stepsLeft: 2 });
  const kept = held(notice('d0001', 2));
  assert.deepEqual(kept, { sessionId: 'session', decisionId: 'd0001', stepsLeft: 2 }, '유지(keep)되어 반복된 응답에도 남음');
  assert.equal(held(notice('d0001', 2)), kept, '같은 값이면 그대로');
  assert.equal(held(notice('d0001', 1)).stepsLeft, 1, '남은 단계 수를 따라감');
  assert.equal(held({ ...notice('d0001', 1), ai_available: false }).stepsLeft, 1, 'ai_available false 응답도 그 결정을 실음');
  assert.equal(held(switched({ preset: 'none' })), null, '결정이 없는 응답에 끝남');
  assert.equal(held(notice('d0001', 1)), null, '끝난 결정 ID로는 다시 띄우지 않음');
  assert.equal(held(notice('d0002', 2)).decisionId, 'd0002', '새 결정은 새 안내');
  assert.equal(held(wait), null, '다른 결정(3-2 기다림)에 끝남');
  assert.equal(held(notice('d0004', 2)).decisionId, 'd0004');
  read.endNotice(); // 화면 전환·세션 변경·전송 멈춤
  assert.equal(held(notice('d0004', 2)), null, '끝낸 뒤 같은 결정 ID로는 다시 띄우지 않음');
  // 강조는 지금처럼 결정 ID마다 한 번만 실행합니다.
  const ring = switched({ ...highlight.support, decision_id: 'd0005' });
  assert.equal(read(ring, 'session').action?.kind, 'highlight');
  assert.equal(read(ring, 'session').action, null);
  // 시연 스위치를 끈 응답(이름 없음)에는 안내가 없습니다.
  const off = createDecisionReader();
  for (const preset of ['none', 'step_guide', 'large_text']) assert.equal(off(switched({ preset }), 'session').notice, null);
});

test('응답이 끊겨 내린 3-1 안내는 같은 결정 ID를 다시 실은 응답에 되살아나고, 결정 없는 응답으로 끝난 안내는 되살아나지 않는다', () => {
  const read = createDecisionReader();
  const notice = (decision_id, steps_left) => switched({ ...stepsNotice.support, decision_id, steps_left });
  const held = response => read(response, 'session').notice;
  assert.equal(held(notice('d0001', 2)).stepsLeft, 2);
  read.pauseNotice(); // 전송기 상태 error·stopped·idle
  read.pauseNotice(); // 확인 주기마다 다시 불려도 같음
  assert.deepEqual(held(notice('d0001', 1)), { sessionId: 'session', decisionId: 'd0001', stepsLeft: 1 }, '같은 결정 ID로 되살아나고 수를 따라감');
  assert.equal(held(notice('d0001', 1)).stepsLeft, 1, '그 뒤에도 남음');
  read.pauseNotice();
  assert.equal(held(switched({ preset: 'none' })), null, '내린 뒤 결정 없는 응답이 오면 상태가 끝남');
  assert.equal(held(notice('d0001', 1)), null, '상태가 끝난 결정 ID로는 되살아나지 않음');
  // 결정 없는 응답으로 끝난 안내는 그 뒤에 내려도 되살아나지 않습니다.
  assert.equal(held(notice('d0002', 2)).decisionId, 'd0002');
  assert.equal(held(wait), null);
  read.pauseNotice();
  assert.equal(held(notice('d0002', 2)), null);
  // 화면·세션 변경(endNotice)은 내린 안내도 끝냅니다.
  assert.equal(held(notice('d0004', 2)).decisionId, 'd0004');
  read.pauseNotice(); read.endNotice();
  assert.equal(held(notice('d0004', 2)), null);
});

test('4-2 강조는 같은 결정을 실은 응답 동안 남고, 기다림·안내·결정 없는 응답으로 바뀌면 내린다', () => {
  const read = createDecisionReader();
  const ring = decision_id => switched({ ...highlight.support, decision_id });
  const shown = response => read(response, 'session');
  assert.deepEqual(shown(ring('d0101')).highlight, { sessionId: 'session', decisionId: 'd0101', targetId: 'cart-add' });
  const kept = shown(ring('d0101')).highlight;
  assert.equal(kept?.decisionId, 'd0101', '같은 결정의 반복에는 남음');
  assert.equal(shown(switched({ name: 'wait_hold_timer', decision_id: 'd0102' })).highlight, null, '3-2 기다림으로 바뀌면 내림');
  assert.equal(shown(ring('d0101')).highlight, null, '내린 결정 ID로는 다시 띄우지 않음');
  assert.equal(shown(ring('d0103')).highlight?.decisionId, 'd0103');
  const replaced = shown(switched({ ...stepsNotice.support, decision_id: 'd0104' }));
  assert.equal(replaced.highlight, null, '3-1 안내로 바뀌면 내림');
  assert.equal(replaced.notice?.decisionId, 'd0104', '안내는 뜸');
  assert.equal(shown(ring('d0105')).highlight?.decisionId, 'd0105');
  assert.equal(shown(switched({ preset: 'none' })).highlight, null, '결정 없는 응답에 내림');
  // 고객의 다음 터치·화면 전환(endHighlight) 뒤에는 같은 결정이 계속 와도 다시 띄우지 않습니다.
  assert.equal(shown(ring('d0106')).highlight?.decisionId, 'd0106');
  read.endHighlight();
  assert.equal(shown(ring('d0106')).highlight, null);
});

test('같은 결정 ID에는 세션마다 한 번만 반응한다', () => {
  const first = createDecisionGate();
  assert.equal(first('session', 'd0001'), true);
  assert.equal(first('session', 'd0001'), false, '유지되어 반복된 결정');
  assert.equal(first('session', 'd0001'), false);
  assert.equal(first('session', 'd0002'), true, '바뀐 결정');
  assert.equal(first('next-session', 'd0001'), true, '새 세션은 처음부터');
  assert.equal(first('next-session', 'd0001'), false);
});

test('API 값과 화면 표시를 구분하고 푸드 온도는 null로 다룬다', () => {
  assert.equal(categoryLabels.coffee, '커피');
  assert.equal(categoryLabels.drink, '음료');
  assert.equal(categoryLabels.food, '푸드');
  assert.equal(temperatureLabel('iced'), '아이스');
  assert.equal(temperatureLabel('hot'), '핫');
  assert.equal(temperatureLabel(null), '기본');
  assert.equal(money(12500), '12,500원');
});
test('고객 화면의 온도 이름은 아이스·핫이고 푸드에는 온도를 쓰지 않는다', () => {
  assert.equal(temperatureText('iced'), '아이스');
  assert.equal(temperatureText('hot'), '핫');
  // 개발 샘플과 서버 주문번호 모두 원래 값을 보여 모의 번호의 접두사를 숨기지 않습니다.
  assert.equal(orderNumberText('DEV-SAMPLE-001'), 'DEV-SAMPLE-001');
  assert.equal(orderNumberText('DEMO-042'), 'DEMO-042');
  assert.equal(orderNumberText('A001'), 'A001');
  assert.equal(temperatureText(null), '');
  assert.equal(temperatureLabel('iced'), '아이스');
});
test('이전 저장 데이터에서는 화면 설정만 읽고 로컬 장바구니를 복원하지 않는다', () => {
  const legacy = { cart: [{ productId: 'latte', temperature: '핫', quantity: 3 }], settings: { ...initialSettings, largeText: true } };
  assert.deepEqual(readSettings(JSON.stringify(legacy)), legacy.settings);
  assert.deepEqual(readSettings(JSON.stringify(legacy.settings)), legacy.settings);
  assert.equal('cart' in readSettings(JSON.stringify(legacy)), false);
});
test('손상된 저장 설정과 boolean이 아닌 값은 기본 설정으로 처리한다', () => {
  assert.deepEqual(readSettings('{broken'), initialSettings);
  assert.deepEqual(readSettings(JSON.stringify({ largeText: 'false' })), initialSettings);
});

test('낮은 화면 설정을 복원하고 이전 저장 형식에서는 기본 높이를 사용한다', () => {
  const oldSettings = { largeText: true, largeButton: false, simpleScreen: false, stepGuide: true };
  assert.deepEqual(readSettings(JSON.stringify(oldSettings)), { ...oldSettings, lowScreen: false, highContrast: false });
  assert.deepEqual(readSettings(JSON.stringify({ ...oldSettings, lowScreen: true })), { ...oldSettings, lowScreen: true, highContrast: false });
  assert.deepEqual(readSettings(JSON.stringify({ ...oldSettings, lowScreen: 'true' })), { ...oldSettings, lowScreen: false, highContrast: false });
});

const emptyCart = (session = 'session-1') => ({ session_id: session, version: 0, currency: 'KRW', items: [], total_quantity: 0, total_amount: 0, updated_at: '2026-10-09T00:00:00Z' });
const populatedCart = (version = 1) => ({ ...emptyCart(), version,
  items: [{ item_id: 'item-1', product_id: 'americano', name: '아메리카노', temperature: 'iced', quantity: 2, unit_price: 3500, line_amount: 7000 }],
  total_quantity: 2, total_amount: 7000 });
const order = { order_id: 'order-1', order_number: 'A042', session_id: 'session-1', status: 'simulated', currency: 'KRW',
  items: populatedCart().items, total_quantity: 2, total_amount: 7000, created_at: '2026-10-09T00:01:00Z' };
function fixture(overrides = {}, onInvalidOrder) {
  let sessions = 0;
  const api = {
    getProducts: async () => ({ currency: 'KRW', products: [] }),
    createSession: async () => ({ session_id: `session-${++sessions}`, started_at: '2026-10-09T00:00:00Z' }),
    getCart: async session => emptyCart(session),
    ...overrides,
  };
  return new OrderController(api, onInvalidOrder);
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('초기화 중 중복 호출은 상품·세션 요청을 한 번만 실행한다', async () => {
  let calls = 0;
  const controller = fixture({ createSession: async () => { calls++; return { session_id: 'session-1', started_at: '' }; } });
  await Promise.all([controller.initialize(), controller.initialize()]);
  assert.equal(calls, 1);
  assert.equal(controller.getSnapshot().status, 'ready');
});

test('확인한 처음으로 동작은 새 서버 세션을 만들고 미확정 요청은 버리지 않는다', async () => {
  const controller = fixture();
  await controller.initialize();
  const previous = controller.getSnapshot().session.session_id;
  assert.equal(await controller.restartCurrentOrder(), true);
  assert.notEqual(controller.getSnapshot().session.session_id, previous);
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
  const uncertain = fixture({ addCartItem: async () => { throw new TypeError('response lost'); } });
  await uncertain.initialize();
  await uncertain.addItem({ product_id: 'americano', temperature: 'iced', quantity: 1 });
  const session = uncertain.getSnapshot().session.session_id;
  assert.equal(await uncertain.restartCurrentOrder(), false);
  assert.equal(uncertain.getSnapshot().session.session_id, session);
  assert.equal(uncertain.getSnapshot().status, 'uncertain');
});

test('주문 API가 없는 서버에서는 연결 대기를 표시하고 로컬 상품·Cart로 대체하지 않는다', async () => {
  let sessions = 0;
  const controller = fixture({
    getProducts: async () => { throw new ApiError(404, { detail: 'Not Found' }); },
    createSession: async () => { sessions++; return { session_id: 'session-1', started_at: '' }; },
  });
  assert.equal(await controller.initialize(), false);
  assert.equal(controller.getSnapshot().status, 'disconnected');
  assert.match(controller.getSnapshot().message, /아직 준비되지/);
  assert.equal(controller.getSnapshot().cart, null);
  assert.deepEqual(controller.getSnapshot().products, []);
  assert.equal(sessions, 0);
});

test('추가 응답 전에는 기존 상태를 유지하고 처리 중 중복 클릭을 막는다', async () => {
  let finish, calls = 0;
  const controller = fixture({ addCartItem: () => { calls++; return new Promise(resolve => { finish = resolve; }); } });
  await controller.initialize();
  const first = controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 });
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
  assert.equal(controller.getSnapshot().status, 'saving');
  assert.equal(await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 }), false);
  finish(populatedCart());
  assert.equal(await first, true);
  assert.equal(controller.getSnapshot().cart.total_amount, 7000);
  assert.equal(calls, 1);
});

test('응답 유실 재시도는 같은 키·버전·본문을 유지하고 새 변경을 막는다', async () => {
  const requests = [];
  const controller = fixture({ addCartItem: async (...args) => {
    requests.push(structuredClone(args));
    if (requests.length === 1) throw new TypeError('response lost');
    return populatedCart();
  } });
  await controller.initialize();
  const input = { product_id: 'americano', temperature: 'iced', quantity: 2 };
  assert.equal(await controller.addItem(input), false);
  input.quantity = 10;
  assert.equal(controller.getSnapshot().status, 'uncertain');
  assert.equal(await controller.checkout(), false);
  assert.equal(await controller.addItem(input), false);
  assert.equal(await controller.retry(), true);
  assert.deepEqual(requests[0], requests[1]);
  assert.equal(controller.getSnapshot().cart.total_quantity, 2);
});

test('버전 충돌은 최신 Cart를 표시하고 사용자 재조작에 새 키를 쓴다', async () => {
  const requests = [], latest = populatedCart(5);
  const controller = fixture({ getCart: async () => populatedCart(1), updateCartItem: async (...args) => {
    requests.push(args);
    if (requests.length === 1) throw new ApiError(409, { code: 'cart_version_conflict', detail: '최신 내용을 확인해주세요.', cart: latest });
    return { ...latest, version: 6 };
  } });
  await controller.initialize();
  assert.equal(await controller.updateQuantity('item-1', 3), false);
  assert.equal(requests.length, 1);
  assert.equal(controller.getSnapshot().cart.version, 5);
  assert.equal(await controller.retry(), false);
  assert.equal(await controller.updateQuantity('item-1', 3), true);
  assert.equal(requests[1][2].expected_version, 5);
  assert.notEqual(requests[0][3], requests[1][3]);
});

test('낮은 버전 응답으로 현재 Cart를 덮어쓰지 않는다', async () => {
  const controller = fixture({ getCart: async () => populatedCart(5), updateCartItem: async () => populatedCart(2) });
  await controller.initialize();
  await controller.updateQuantity('item-1', 3);
  assert.equal(controller.getSnapshot().cart.version, 5);
});

test('음성 장바구니 변경 뒤에는 최신 Cart를 다시 읽고, 실패해도 이전 Cart를 보존한다', async () => {
  let reads = 0;
  const latest = { ...populatedCart(3), items: [{ ...populatedCart().items[0], quantity: 3, line_amount: 10500 }], total_quantity: 3, total_amount: 10500 };
  const controller = fixture({ getCart: async () => {
    reads += 1;
    if (reads === 1) return populatedCart(1);
    if (reads === 2) return latest;
    throw new ApiError(503, { detail: 'temporary failure' });
  } });
  await controller.initialize();
  assert.equal(await controller.refreshCartAfterVoice(), true);
  assert.equal(controller.getSnapshot().cart.total_quantity, 3);
  assert.match(controller.getSnapshot().notice, /음성 주문/);
  assert.equal(await controller.refreshCartAfterVoice(), false);
  assert.equal(controller.getSnapshot().status, 'ready');
  assert.equal(controller.getSnapshot().cart.total_quantity, 3);
  assert.match(controller.getSnapshot().message, /음성 주문 결과/);
});

test('터치 응답보다 먼저 온 음성 변경은 저장 뒤 한 번 조회하고 다음 변경에 최신 버전을 쓴다', async () => {
  const touch = deferred(), refresh = deferred();
  let reads = 0, nextVersion;
  const controller = fixture({
    getCart: () => ++reads === 1 ? Promise.resolve(emptyCart()) : refresh.promise,
    addCartItem: () => touch.promise,
    updateCartItem: async (_session, _item, input) => { nextVersion = input.expected_version; return populatedCart(3); },
  });
  await controller.initialize();
  const writing = controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 });
  await controller.refreshCartAfterVoice();
  await controller.refreshCartAfterVoice();
  assert.equal(reads, 1, '터치 저장 중에는 재조회를 보류');
  touch.resolve(populatedCart(1));
  assert.equal(await writing, true);
  assert.equal(reads, 2, '저장 중의 알림들을 한 번의 조회로 처리');
  assert.equal(controller.getSnapshot().status, 'saving');
  assert.equal(await controller.updateQuantity('item-1', 3), false, '재조회가 끝나기 전에는 추가 변경 차단');
  refresh.resolve(populatedCart(2));
  await refresh.promise;
  assert.equal(controller.getSnapshot().status, 'ready');
  assert.equal(controller.getSnapshot().cart.version, 2);
  assert.equal(await controller.updateQuantity('item-1', 3), true);
  assert.equal(nextVersion, 2);
});

test('음성 재조회 도중 새 변경이 오면 현재 조회 뒤 한 번 더 조회하고 중간에 조작을 열지 않는다', async () => {
  const first = deferred(), second = deferred();
  let reads = 0;
  const controller = fixture({ getCart: () => {
    reads++;
    return reads === 1 ? Promise.resolve(populatedCart(1)) : reads === 2 ? first.promise : second.promise;
  } });
  await controller.initialize();
  const snapshots = [];
  controller.subscribe(() => snapshots.push(controller.getSnapshot()));
  const refreshing = controller.refreshCartAfterVoice();
  await controller.refreshCartAfterVoice();
  await controller.refreshCartAfterVoice();
  assert.equal(reads, 2);
  first.resolve(populatedCart(2));
  await refreshing;
  assert.equal(reads, 3);
  assert.equal(controller.getSnapshot().status, 'saving');
  assert(!snapshots.some(snapshot => snapshot.status === 'ready'), '중간 응답으로 조작을 재개하지 않음');
  second.resolve(populatedCart(3));
  await second.promise;
  assert.equal(controller.getSnapshot().status, 'ready');
  assert.equal(controller.getSnapshot().cart.version, 3);
});

test('응답 유실 중 음성 변경은 동일 요청 재확인이 끝난 뒤 조회한다', async () => {
  const requests = [], refresh = deferred();
  let reads = 0;
  const controller = fixture({
    getCart: () => ++reads === 1 ? Promise.resolve(emptyCart()) : refresh.promise,
    addCartItem: async (...args) => {
      requests.push(structuredClone(args));
      if (requests.length === 1) throw new TypeError('response lost');
      return populatedCart(1);
    },
  });
  await controller.initialize();
  await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 2 });
  await controller.refreshCartAfterVoice();
  assert.equal(controller.getSnapshot().status, 'uncertain');
  assert.equal(reads, 1, '음성 조회로 미확정 요청을 버리지 않음');
  assert.equal(await controller.retry(), true);
  assert.deepEqual(requests[0], requests[1]);
  assert.equal(reads, 2);
  refresh.resolve(populatedCart(2));
  await refresh.promise;
  assert.equal(controller.getSnapshot().cart.version, 2);
});

test('터치 요청이 확정 오류로 끝나도 보류한 음성 변경은 조회한다', async () => {
  const touch = deferred(), refresh = deferred();
  let reads = 0;
  const controller = fixture({
    getCart: () => ++reads === 1 ? Promise.resolve(populatedCart(1)) : refresh.promise,
    updateCartItem: () => touch.promise,
  });
  await controller.initialize();
  const writing = controller.updateQuantity('item-1', 3);
  await controller.refreshCartAfterVoice();
  touch.reject(new ApiError(409, { code: 'cart_version_conflict', detail: '최신 내용을 확인해주세요.', cart: populatedCart(2) }));
  assert.equal(await writing, false);
  assert.equal(reads, 2);
  refresh.resolve(populatedCart(3));
  await refresh.promise;
  assert.equal(controller.getSnapshot().cart.version, 3);
});

test('세션이 끝나면 보류한 음성 조회를 버리고 새 주문에 가져가지 않는다', async () => {
  const touch = deferred(), sessions = [];
  const controller = fixture({
    getCart: async session => { sessions.push(session); return session === 'session-1' ? populatedCart(1) : emptyCart(session); },
    updateCartItem: () => touch.promise,
  });
  await controller.initialize();
  const writing = controller.updateQuantity('item-1', 3);
  await controller.refreshCartAfterVoice();
  touch.reject(new ApiError(410, { code: 'session_expired', detail: '새로 시작해주세요.', cart: null }));
  await writing;
  assert.equal(controller.getSnapshot().status, 'ended');
  assert.deepEqual(sessions, ['session-1']);
  assert.equal(await controller.startNewOrder(), true);
  assert.deepEqual(sessions, ['session-1', 'session-2']);
  assert.equal(controller.getSnapshot().cart.session_id, 'session-2');
});

test('주문 완료로 확정되면 보류한 음성 조회가 완료 Cart를 다시 읽지 않는다', async () => {
  const checkout = deferred(), sessions = [];
  const controller = fixture({
    getCart: async session => { sessions.push(session); return session === 'session-1' ? populatedCart(1) : emptyCart(session); },
    createOrder: () => checkout.promise,
  });
  await controller.initialize();
  const writing = controller.checkout();
  await controller.refreshCartAfterVoice();
  checkout.resolve(structuredClone(order));
  assert.equal(await writing, true);
  assert.equal(controller.getSnapshot().order.order_id, order.order_id);
  assert.equal(controller.getSnapshot().cart, null);
  assert.deepEqual(sessions, ['session-1']);
  assert.equal(await controller.startNewOrder(), true);
  assert.deepEqual(sessions, ['session-1', 'session-2']);
});

test('처리 중 응답의 재시도 간격을 존중하고 그동안 새 키를 만들지 않는다', async () => {
  let calls = 0;
  const controller = fixture({ addCartItem: async () => {
    calls++;
    // 처리 중 오류 코드는 미정입니다. 서버가 제공한 Retry-After를 사용합니다.
    throw new ApiError(409, { code: 'pending_example', detail: '처리 중', cart: null }, 0.02);
  } });
  await controller.initialize();
  await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 1 });
  assert.equal(await controller.retry(), false);
  assert.equal(calls, 1);
  await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(controller.getSnapshot().retryAt, 0);
});

test('주문 실패는 Cart를 유지하고 응답 유실 재확인으로 서버 주문번호를 표시한다', async () => {
  const requests = [];
  const controller = fixture({ getCart: async session => session === 'session-1' ? populatedCart() : emptyCart(session), createOrder: async (...args) => {
    requests.push(args);
    if (requests.length === 1) throw new ApiError(409, { code: 'product_unavailable', detail: '품절', cart: null });
    if (requests.length === 2) throw new TypeError('response lost');
    return order;
  } });
  await controller.initialize();
  assert.equal(await controller.checkout(), false);
  assert.equal(controller.getSnapshot().cart.total_amount, 7000);
  assert.equal(controller.getSnapshot().order, null);
  assert.equal(await controller.checkout(), false);
  assert.equal(await controller.retry(), true);
  assert.deepEqual(requests[1], requests[2]);
  assert.equal(controller.getSnapshot().order.order_number, 'A042');
  assert.equal(await controller.checkout(), false);
  assert.equal(await controller.startNewOrder(), true);
  assert.equal(controller.getSnapshot().session.session_id, 'session-2');
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
});

test('세션 소실은 새 이용 시작을 안내하고 로컬 Cart로 복구하지 않는다', async () => {
  const controller = fixture({ getCart: async session => session === 'session-1' ? populatedCart() : emptyCart(session),
    updateCartItem: async () => { throw new ApiError(404, { code: 'session_not_found', detail: '새로 시작해주세요.', cart: null }); } });
  await controller.initialize();
  await controller.updateQuantity('item-1', 3);
  assert.equal(controller.getSnapshot().status, 'ended');
  assert.equal(await controller.startNewOrder(), true);
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
});

test('코드 없는 404·410과 접근 오류 뒤에는 새 서버 세션으로 시작할 수 있다', async () => {
  for (const status of [404, 410, 401, 403]) {
    const controller = fixture({ getCart: async session => session === 'session-1' ? populatedCart() : emptyCart(session),
      updateCartItem: async () => { throw new ApiError(status, { detail: 'session not found' }); } });
    await controller.initialize();
    assert.equal(await controller.updateQuantity('item-1', 3), false);
    assert.equal(controller.getSnapshot().status, 'ended', `HTTP ${status}`);
    assert.equal(await controller.startNewOrder(), true);
    assert.equal(controller.getSnapshot().session.session_id, 'session-2');
    assert.equal(controller.getSnapshot().cart.total_quantity, 0);
  }
});

test('상품·장바구니 항목 없음 404는 현재 세션과 장바구니를 유지한다', async () => {
  for (const code of ['product_not_found', 'cart_item_not_found']) {
    const controller = fixture({ getCart: async () => populatedCart(),
      updateCartItem: async () => { throw new ApiError(404, { code, detail: '항목을 찾을 수 없습니다.', cart: null }); } });
    await controller.initialize();
    await controller.updateQuantity('item-1', 3);
    assert.equal(controller.getSnapshot().status, 'ready', code);
    assert.equal(controller.getSnapshot().session.session_id, 'session-1');
    assert.equal(controller.getSnapshot().cart.total_quantity, 2);
    assert.equal(await controller.startNewOrder(), false);
  }
});

test('재확인 실패 뒤에만 대기 요청을 버리고 새 주문을 시작할 수 있다', async () => {
  const requests = [];
  let failRetry;
  const controller = fixture({ getCart: async session => session === 'session-1' ? populatedCart() : emptyCart(session),
    createOrder: (...args) => {
      requests.push(structuredClone(args));
      return requests.length === 1 ? Promise.reject(new TypeError('response lost'))
        : new Promise((resolve, reject) => { failRetry = reject; });
    } });
  await controller.initialize();
  assert.equal(await controller.checkout(), false);
  assert.equal(controller.getSnapshot().canAbandonPending, false);
  assert.equal(controller.abandonPending(), false);
  const retry = controller.retry();
  assert.equal(controller.getSnapshot().status, 'saving');
  assert.equal(controller.abandonPending(), false, '처리 중인 요청은 버리지 않음');
  assert.equal(await controller.startNewOrder(), false);
  failRetry(new ApiError(503, { detail: '처리 결과를 확인할 수 없습니다.' }, 0.02));
  assert.equal(await retry, false);
  assert.deepEqual(requests[0], requests[1], '재확인은 같은 키·버전·본문');
  assert.equal(controller.getSnapshot().canAbandonPending, true);
  assert.match(controller.getSnapshot().abandonWarning, /이전 주문은 자동으로 취소되지/);
  assert.equal(controller.getSnapshot().cart.total_amount, 7000);
  assert.equal(controller.abandonPending(), true);
  assert.equal(controller.getSnapshot().status, 'ended');
  assert.equal(controller.getSnapshot().retryAt, 0);
  assert.equal(controller.getSnapshot().canAbandonPending, false);
  assert.equal(await controller.retry(), false);
  assert.equal(await controller.startNewOrder(), true);
  assert.equal(controller.getSnapshot().session.session_id, 'session-2');
  assert.equal(controller.getSnapshot().cart.total_quantity, 0);
  assert.equal(controller.getSnapshot().order, null);
  assert.equal(requests.length, 2, '이전 요청을 새 세션에서 다시 실행하지 않음');
});

test('불완전한 주문 성공 응답은 Cart와 정확한 요청을 유지하고 유효한 재확인 후에만 완료한다', async () => {
  const invalid = [null, [], { session_id: 'session-1' }];
  for (const field of Object.keys(order)) {
    const missing = structuredClone(order);
    delete missing[field];
    invalid.push(missing);
  }
  for (const patch of [
    { order_id: '' }, { order_number: 42 }, { status: 'paid' }, { currency: 'USD' }, { items: [] },
    { total_quantity: 1.5 }, { total_amount: -1 }, { total_amount: 100 }, { created_at: 'yesterday' },
    { created_at: '2026-10-09' }, { items: [{ ...order.items[0], quantity: 21 }] },
    { items: [{ ...order.items[0], temperature: 'warm' }] },
    { items: [{ ...order.items[0], line_amount: '7000' }] },
  ]) invalid.push({ ...structuredClone(order), ...patch });
  for (const field of Object.keys(order.items[0])) {
    const broken = structuredClone(order);
    delete broken.items[0][field];
    invalid.push(broken);
  }
  for (const response of invalid) {
    const requests = [];
    const diagnostics = [];
    const controller = fixture({ getCart: async () => populatedCart(), createOrder: async (...args) => {
      requests.push(structuredClone(args));
      return requests.length === 1 ? response : structuredClone(order);
    } }, fields => diagnostics.push([...fields]));
    await controller.initialize();
    assert.equal(await controller.checkout(), false, JSON.stringify(response));
    assert.equal(controller.getSnapshot().status, 'uncertain');
    assert.equal(diagnostics.length, 1);
    assert(diagnostics[0].length > 0);
    assert.equal(controller.getSnapshot().order, null);
    assert.deepEqual(controller.getSnapshot().cart, populatedCart());
    assert.equal(await controller.checkout(), false);
    assert.equal(await controller.retry(), true);
    assert.deepEqual(requests[0], requests[1]);
    assert.equal(controller.getSnapshot().order.order_number, 'A042');
    assert.equal(controller.getSnapshot().cart, null);
  }
});

test('주문 응답 진단은 잘못된 필드 경로만 제공하고 응답 값은 보관하지 않는다', () => {
  const broken = structuredClone(order);
  broken.items[0].temperature = 'private-value';
  broken.total_amount = 99;
  assert.throws(() => readOrderResponse(broken), error => {
    assert(error instanceof OrderResponseError);
    assert.deepEqual(error.fields, ['items[0].temperature']);
    assert.equal('body' in error, false);
    assert(!JSON.stringify(error).includes('private-value'));
    return true;
  });
  assert.throws(() => readOrderResponse({ ...order, total_amount: 99 }), error => {
    assert.deepEqual(error.fields, ['total_amount']);
    return true;
  });
});

test('장바구니 변경 재확인과 새 시작은 주문 취소 안내를 표시하지 않는다', async () => {
  const controller = fixture({ addCartItem: async () => { throw new TypeError('response lost'); } });
  await controller.initialize();
  await controller.addItem({ product_id: 'americano', temperature: 'iced', quantity: 1 });
  await controller.retry();
  assert.match(controller.getSnapshot().message, /메뉴 변경/);
  assert.match(controller.getSnapshot().abandonWarning, /새 장바구니/);
  assert.doesNotMatch(controller.getSnapshot().abandonWarning, /주문은 자동으로 취소/);
  assert(controller.abandonPending());
  assert.match(controller.getSnapshot().message, /이전 메뉴 변경/);
});

test('Cart 조회가 실패해도 받은 서버 세션을 기록하고 재연결은 새 세션으로 시도한다', async () => {
  let carts = 0;
  const controller = fixture({ getCart: async session => {
    if (++carts === 1) throw new ApiError(503, { detail: '연결 대기' });
    return emptyCart(session);
  } });
  await controller.initialize();
  assert.equal(controller.getSnapshot().status, 'disconnected');
  assert.equal(controller.getSnapshot().session.session_id, 'session-1');
  assert.equal(controller.getSnapshot().cart, null);
  assert.equal(await controller.initialize(), true);
  assert.equal(controller.getSnapshot().session.session_id, 'session-2');
  assert.equal(controller.getSnapshot().status, 'ready');
});

test('메뉴는 화면 설정에 맞는 수로 쪽을 나누고 범위를 벗어난 쪽을 마지막 쪽으로 되돌린다', () => {
  const mode = (settings = {}) => ({ largeText: false, largeButton: false, lowScreen: false, simpleScreen: false, ...settings });
  assert.equal(menuPageSize(mode()), 9, '기본: 사진 카드 3 × 3, 17개 메뉴는 2쪽');
  assert.equal(menuPageSize(mode({ largeButton: true })), 9);
  assert.equal(menuPageSize(mode({ stepGuide: true })), 6, '단계별 안내 줄이 서면 한 줄 줄어듦');
  assert.equal(menuPageSize(mode({ largeText: true })), 4, '큰 글씨: 사진 카드 2 × 2, 17개 메뉴는 5쪽');
  assert.equal(menuColumns(mode({ largeText: true })), 2);
  assert.equal(menuPageSize(mode({ largeText: true, stepGuide: true })), 2, '큰 글씨 + 단계별 안내: 사진 카드 한 줄');
  assert.equal(menuPageSize(mode({ largeText: true, voiceOn: true })), 2, '큰 글씨 + 말로 주문: 사진 카드 한 줄');
  assert.equal(menuPageSize(mode({ largeText: true, simpleScreen: true, stepGuide: true })), 4, '큰 글씨 + 간편 화면: 글자 줄 4개');
  assert.equal(menuColumns(mode({ largeText: true, simpleScreen: true })), 1);
  assert.equal(menuPageSize(mode({ lowScreen: true })), 6);
  assert.equal(menuPageSize(mode({ lowScreen: true, stepGuide: true })), 3);
  assert.equal(menuPageSize(mode({ lowScreen: true, largeText: true })), 2);
  assert.equal(menuPageSize(mode({ simpleScreen: true })), 10);
  assert.equal(menuPageSize(mode({ simpleScreen: true, largeButton: true, lowScreen: true, stepGuide: true })), 5);
  assert.equal(menuPageSize(mode({ voiceOn: true })), 6, '말로 주문: 사진 카드 2 × 3');
  assert.equal(menuPageSize(mode({ voiceOn: true, stepGuide: true })), 6, '말로 주문 중에는 단계별 안내가 없음');
  assert.equal(menuPageSize(mode({ voiceOn: true, largeButton: true })), 3);
  assert.equal(menuPageSize(mode({ voiceOn: true, simpleScreen: true })), 5, '말로 주문 + 간편 화면: 글자 줄 5개(담은 메뉴 위 32 px를 지킴)');
  assert.equal(menuPageSize(mode({ largeView: true })), 6, '크게 보기: 세 열 두 줄, 17개 메뉴는 3쪽');
  assert.equal(menuPageSize(mode({ largeView: true, lowScreen: true })), 3, '낮은 화면 + 크게 보기: 세 열 한 줄');
  const products = Array.from({ length: 17 }, (_, index) => index);
  assert.equal(pageCount(products.length, 6), 3);
  assert.deepEqual([0, 1, 2].map(page => pageItems(products, page, 6).length), [6, 6, 5]);
  assert.equal(pageCount(0, 6), 1, '빈 목록도 한 쪽');
  assert.equal(clampPage(5, products.length, 6), 2);
  assert.equal(clampPage(-1, products.length, 6), 0);
  assert.deepEqual(pageItems(products, 9, 6), [12, 13, 14, 15, 16]);
});

test('주문 확인은 화면 설정과 줄 수에 맞춰 쪽을 나눈다', () => {
  const mode = (settings = {}) => ({ largeText: false, largeButton: false, lowScreen: false, simpleScreen: false, ...settings });
  assert.equal(reviewPageSize(mode(), 0), 1, '빈 주문도 한 줄 자리');
  assert.equal(reviewPageSize(mode(), 4), 4);
  assert.equal(reviewPageSize(mode(), 7), 5, '기본 크기는 다섯 줄까지');
  assert.equal(reviewPageSize(mode({ largeButton: true }), 7), 5);
  assert.equal(reviewPageSize(mode({ largeText: true }), 3), 3);
  assert.equal(reviewPageSize(mode({ largeText: true }), 4), 2);
  assert.equal(reviewPageSize(mode({ lowScreen: true }), 3), 3);
  assert.equal(reviewPageSize(mode({ lowScreen: true }), 4), 2);
  assert.equal(reviewPageSize(mode({ lowScreen: true, largeButton: true }), 3), 2);
  assert.equal(reviewPageSize(mode({ lowScreen: true, largeText: true }), 3), 1);
  assert.equal(pageCount(17, reviewPageSize(mode(), 17)), 4);
});
