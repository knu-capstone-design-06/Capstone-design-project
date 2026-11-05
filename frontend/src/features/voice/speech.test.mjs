import assert from 'node:assert/strict';
import test from 'node:test';
import { createReplySpeaker } from './replySpeech.ts';
import { createSpeechCapture, findRecognition, isSpeechSupported } from './speech.ts';
import { FakeRecognition, factory, tick } from './voiceFakes.mjs';

function capture(options) {
  const events = [];
  const handle = createSpeechCapture(factory, {
    onPartial: text => events.push(['partial', text]),
    onFinal: result => events.push(['final', result]),
    onError: code => events.push(['error', code]),
    onEnd: reason => events.push(['end', reason]),
  }, options);
  return { events, handle };
}

function synthesisFixture() {
  const spoken = [];
  const voices = [{ lang: 'en-US', localService: true }, { lang: 'ko-KR', localService: false }, { lang: 'ko-KR', localService: true }];
  let cancellations = 0;
  const scope = {
    SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
    speechSynthesis: { getVoices: () => voices, speak: utterance => spoken.push(utterance), cancel: () => { cancellations++; } },
  };
  return { spoken, scope, voices, cancellations: () => cancellations };
}

test('응답 읽기는 한국어 로컬 음성을 우선 선택하고 완료를 기다린다', async () => {
  const f = synthesisFixture();
  const pending = createReplySpeaker(f.scope)(' 온도를 골라 주세요. ', new AbortController().signal);
  assert.equal(f.spoken[0].text, '온도를 골라 주세요.');
  assert.equal(f.spoken[0].lang, 'ko-KR');
  assert.equal(f.spoken[0].voice, f.voices[2]);
  f.spoken[0].onend();
  assert.equal(await pending, true);
  assert.equal(f.cancellations(), 0);
});

test('응답 읽기는 취소·재생 오류·시간 초과 뒤 늦은 완료를 무시한다', async () => {
  for (const cause of ['abort', 'error', 'timeout']) {
    const f = synthesisFixture(), controller = new AbortController();
    const pending = createReplySpeaker(f.scope, cause === 'timeout' ? 5 : 1000)('아이스로 할까요?', controller.signal);
    const lateEnd = f.spoken[0].onend;
    if (cause === 'abort') controller.abort();
    if (cause === 'error') f.spoken[0].onerror();
    assert.equal(await pending, false, cause);
    lateEnd();
    assert.equal(f.cancellations(), 1);
  }
});

test('음성 합성 미지원·빈 문장·취소된 요청·시작 실패는 읽기 실패로 반환한다', async () => {
  assert.equal(await createReplySpeaker({})('질문', new AbortController().signal), false);
  const f = synthesisFixture(), controller = new AbortController();
  assert.equal(await createReplySpeaker(f.scope)(' ', controller.signal), false);
  controller.abort();
  assert.equal(await createReplySpeaker(f.scope)('질문', controller.signal), false);
  assert.equal(f.spoken.length, 0);
  f.scope.speechSynthesis.speak = () => { throw new Error('blocked'); };
  assert.equal(await createReplySpeaker(f.scope)('질문', new AbortController().signal), false);
});

test('Chrome의 webkit 접두어 인식기를 찾고 없으면 지원하지 않는다', () => {
  class Webkit {}
  class Standard {}
  assert.equal(isSpeechSupported({}), false);
  assert.equal(findRecognition({}), null);
  assert.ok(findRecognition({ webkitSpeechRecognition: Webkit })() instanceof Webkit);
  assert.ok(findRecognition({ SpeechRecognition: Standard, webkitSpeechRecognition: Webkit })() instanceof Standard);
});

test('한국어로 한 문장만 듣고 최종 문장과 후보를 넘긴 뒤 닫는다', () => {
  FakeRecognition.reset();
  const { events, handle } = capture();
  handle.start();
  const recognition = FakeRecognition.last();
  assert.deepEqual(
    [recognition.lang, recognition.maxAlternatives, recognition.continuous, recognition.interimResults, recognition.started],
    ['ko-KR', 5, false, true, 1],
  );
  assert.equal(handle.active, true);
  recognition.partial('아이스 아메');
  recognition.final([' 아이스 아메리카노 두 잔 ', 0.92], ['아이스 아메리카노 두 개', 0]);
  assert.deepEqual(events, [
    ['partial', '아이스 아메'],
    ['final', { text: '아이스 아메리카노 두 잔', alternatives: [
      { text: '아이스 아메리카노 두 잔', confidence: 0.92 },
      { text: '아이스 아메리카노 두 개', confidence: null },
    ] }],
    ['end', 'final'],
  ]);
  assert.equal(recognition.stopped, 1);
  assert.equal(handle.active, false);
});

test('말이 없으면 정한 시간 뒤 마이크를 닫는다', async () => {
  FakeRecognition.reset();
  const { events, handle } = capture({ silenceMs: 20 });
  handle.start();
  await tick(40);
  assert.equal(FakeRecognition.last().aborted, 1);
  assert.deepEqual(events, [['end', 'silence']]);
});

test('권한 거부는 오류로, Chrome의 no-speech는 무음 종료로 알린다', () => {
  FakeRecognition.reset();
  const denied = capture();
  denied.handle.start();
  FakeRecognition.last().fail('not-allowed');
  assert.deepEqual(denied.events, [['error', 'not_allowed'], ['end', 'error']]);

  const silent = capture();
  silent.handle.start();
  FakeRecognition.last().fail('no-speech');
  assert.deepEqual(silent.events, [['end', 'silence']]);
});

test('abort 뒤에 늦게 온 결과는 무시한다', () => {
  FakeRecognition.reset();
  const { events, handle } = capture();
  handle.start();
  const recognition = FakeRecognition.last();
  handle.abort();
  recognition.final(['늦은 결과', 0.9]);
  assert.deepEqual(events, [['end', 'stopped']]);
});
