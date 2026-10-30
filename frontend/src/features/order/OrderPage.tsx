import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react';
import { backendApi } from '../../shared/api/index.ts';
import type { Product, ProductCategory, Temperature } from '../../shared/api/index.ts';
import { categoryLabels, initialSettings, MAX_QUANTITY, money, readSettings, settingsStorageKey, temperatureLabel } from './model.ts';
import type { Settings } from './model.ts';
import { OrderController } from './orderController.ts';
import { orderCopy } from './copy.ts';
import { createSampleOrderApi } from './sampleOrderApi.ts';
import { useTouchLog } from './useTouchLog.ts';
import { captureTouchLogObservation } from './touchLogObservation.ts';
import { TouchLogPanel } from './TouchLogPanel.tsx';
import { VoiceModeToggle } from './VoiceModeToggle.tsx';
import { ReadAloudControls } from './ReadAloudControls.tsx';
import { KioskModeBar } from './KioskModeBar.tsx';
import { KioskClock } from './KioskClock.tsx';
import { createVoiceApi, VoiceController } from '../voice/index.ts';
import './order.css';
import './orderAccessibility.css';
import './kioskReference.css';

const supportLabels: Record<keyof Settings, string> = { largeText: '큰 글씨 (200%)', largeButton: '큰 버튼', simpleScreen: '간편 화면', stepGuide: '단계별 안내', lowScreen: '낮은 화면', highContrast: '고대비' };
const sampleMode = import.meta.env.DEV && import.meta.env.VITE_ORDER_SAMPLE === 'true';

export function OrderPage() {
  const [controller] = useState(() => new OrderController(sampleMode ? createSampleOrderApi() : backendApi, fields => {
    if (import.meta.env.DEV) console.warn('주문 응답 검증 실패 필드:', fields);
  }));
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [voiceController] = useState(() => new VoiceController({ api: createVoiceApi(), recognitionOnly: sampleMode }));
  const voice = useSyncExternalStore(voiceController.subscribe, voiceController.getSnapshot);
  const [settings, setSettings] = useState(() => {
    try { return readSettings(localStorage.getItem(settingsStorageKey) ?? localStorage.getItem('kiosk-sample-order-v1')); }
    catch { return { ...initialSettings }; }
  });
  const [screen, setScreen] = useState<'menu' | 'review' | 'complete'>('menu');
  const [category, setCategory] = useState<ProductCategory | 'all'>('all');
  const [selected, setSelected] = useState<Product | null>(null);
  const [temperature, setTemperature] = useState<Temperature>('iced');
  const [quantity, setQuantity] = useState(1);
  const [supportOpen, setSupportOpen] = useState(false);
  const [storageWarning, setStorageWarning] = useState(false);
  const [orderNumber, setOrderNumber] = useState('');
  const [restartOpen, setRestartOpen] = useState(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const restartDialog = useRef<HTMLDialogElement>(null);
  const restartTrigger = useRef<HTMLButtonElement>(null);
  const actionsRef = useRef<HTMLElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const observation = captureTouchLogObservation(state, selected ? { productId: selected.product_id, temperature, quantity } : null, voice);
  const touchLog = useTouchLog(screen, category === 'all' ? '전체' : categoryLabels[category], selected?.product_id ?? null, settings, state.session?.session_id ?? null, observation);
  useEffect(() => { void controller.initialize(); }, [controller]);
  useEffect(() => {
    voiceController.setEnabled(false);
    voiceController.setContext({ sessionId: state.session?.session_id ?? '', screenId: 'menu_list' });
  }, [voiceController, state.session?.session_id]);
  useEffect(() => {
    if (screen !== 'menu' || (state.status !== 'ready' && state.status !== 'saving') || state.order) voiceController.setEnabled(false);
  }, [voiceController, screen, state.status, state.order]);
  useEffect(() => () => voiceController.dispose(), [voiceController]);
  useEffect(() => { try { localStorage.setItem(settingsStorageKey, JSON.stringify(settings)); } catch { setStorageWarning(true); } }, [settings]);
  useEffect(() => { heading.current?.focus(); }, [screen]);
  useLayoutEffect(() => { if (selected) dialog.current?.showModal(); else if (dialog.current?.open) dialog.current.close(); }, [selected]);
  useLayoutEffect(() => {
    if (restartOpen) restartDialog.current?.showModal();
    else if (restartDialog.current?.open) restartDialog.current.close();
  }, [restartOpen]);
  useEffect(() => {
    const bar = actionsRef.current;
    const root = touchLog.root.current;
    if (!bar || !root) return;
    const measure = () => {
      const height = `${Math.ceil(bar.getBoundingClientRect().height)}px`;
      root.style.setProperty('--order-actions-space', height);
      document.documentElement.style.setProperty('--order-actions-measured-height', height);
      const mainHeight = root.querySelector('main')?.getBoundingClientRect().height ?? innerHeight;
      root.style.setProperty('--order-feedback-space', `${Math.max(120, Math.min(mainHeight, innerHeight - bar.getBoundingClientRect().height) - 48)}px`);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(bar);
    const main = root.querySelector('main'); if (main) observer.observe(main);
    window.addEventListener('resize', measure); measure();
    return () => { observer.disconnect(); window.removeEventListener('resize', measure); document.documentElement.style.removeProperty('--order-actions-measured-height'); };
  }, [touchLog.root]);
  useEffect(() => {
    if (state.message) feedbackRef.current?.scrollIntoView({ block: 'start', behavior: 'instant' });
  }, [state.message, selected]);
  useEffect(() => {
    if (state.order) { setOrderNumber(state.order.order_number); setScreen('complete'); }
  }, [state.order]);

  const busy = state.status === 'loading' || state.status === 'saving';
  const writeDisabled = state.status !== 'ready' || state.order !== null;
  const count = state.cart?.total_quantity ?? 0;
  const sum = state.cart?.total_amount ?? 0;
  const remaining = MAX_QUANTITY - (state.cart?.items.find(item => item.product_id === selected?.product_id && item.temperature === temperature)?.quantity ?? 0);
  const combinedEnlargement = settings.largeText && settings.largeButton;
  function toggleCombinedEnlargement() {
    setSettings(current => {
      const enabled = !(current.largeText && current.largeButton);
      return { ...current, largeText: enabled, largeButton: enabled };
    });
  }
  function toggleScreenHeight() {
    setSettings(current => ({ ...current, lowScreen: !current.lowScreen }));
  }
  function useStandardMode() {
    voiceController.setEnabled(false);
    setSettings(current => ({ ...initialSettings, lowScreen: current.lowScreen }));
  }
  function closeOptions() { setSelected(null); opener.current?.focus(); }
  function closeRestart() { setRestartOpen(false); restartTrigger.current?.focus(); }
  async function addSelected() {
    if (!selected) return;
    if (await controller.addItem({ product_id: selected.product_id, temperature, quantity })) closeOptions();
  }
  async function retry() {
    if (await controller.retry()) closeOptions();
  }
  async function startNewOrder(resetCurrent = false) {
    voiceController.setEnabled(false);
    closeOptions();
    setScreen('menu'); setOrderNumber(''); setCategory('all');
    if (resetCurrent && state.status === 'ready' && !state.order) await controller.restartCurrentOrder();
    else await controller.startNewOrder();
  }
  function openReview() {
    voiceController.setEnabled(false);
    setScreen('review');
  }
  async function restartAfterUncertain() {
    if (!controller.abandonPending()) return;
    setScreen('menu'); setOrderNumber(''); setCategory('all');
    await startNewOrder();
  }
  const feedback = <>{busy && <p className="order-progress" role="status">{state.status === 'loading' ? orderCopy.preparing : orderCopy.saving}</p>}
    {state.message && <div ref={feedbackRef} className="order-feedback" role="alert"><p>{state.message}</p>
      {state.status === 'uncertain' && <>
        {state.canAbandonPending && <p>{state.abandonWarning}</p>}
        <div className="order-feedback-actions">
          <button data-log-target="order-result-retry" disabled={Date.now() < state.retryAt} onClick={() => void retry()}>주문 반영 확인</button>
          {state.canAbandonPending && <button data-log-target="order-pending-restart" onClick={() => void restartAfterUncertain()}>처음부터 다시 주문</button>}
        </div>
      </>}
      {state.status === 'disconnected' && <button data-log-target="order-connect-retry" onClick={() => screen === 'complete' ? void startNewOrder() : void controller.initialize()}>주문 다시 시작</button>}
      {state.status === 'ended' && <button data-log-target="order-session-restart" onClick={() => void startNewOrder()}>처음부터 다시 주문</button>}
    </div>}</>;
  const cartRows = state.cart?.items.map(item => <li key={item.item_id} className="cart-row">
    <div><strong>{item.name}</strong><span>{item.temperature !== null ? `${temperatureLabel(item.temperature)} · ` : ''}{money(item.unit_price)}</span></div>
    <div className="cart-controls"><div className="quantity">
      <button data-log-target={`cart:${item.product_id}:${temperatureLabel(item.temperature)}:decrease`} aria-label={`${item.name} ${temperatureLabel(item.temperature)} 수량 줄이기`} disabled={writeDisabled || item.quantity === 1} onClick={() => void controller.updateQuantity(item.item_id, item.quantity - 1)}>−</button>
      <span>{item.quantity}</span>
      <button data-log-target={`cart:${item.product_id}:${temperatureLabel(item.temperature)}:increase`} aria-label={`${item.name} ${temperatureLabel(item.temperature)} 수량 늘리기`} disabled={writeDisabled || item.quantity === MAX_QUANTITY} onClick={() => void controller.updateQuantity(item.item_id, item.quantity + 1)}>+</button>
    </div><button data-log-target={`cart:${item.product_id}:${temperatureLabel(item.temperature)}:remove`} className="text-button" aria-label={`${item.name} ${temperatureLabel(item.temperature)} 삭제`} disabled={writeDisabled} onClick={() => void controller.removeItem(item.item_id)}>삭제</button></div>
  </li>);

  const screenHeightButton = <button data-log-target="screen-height-toggle" className="screen-height-toggle" data-active={settings.lowScreen} onClick={toggleScreenHeight}>{settings.lowScreen ? '기본 높이' : '낮은 화면'}</button>;

  return <><button type="button" className={`screen-position-pad ${settings.lowScreen ? 'is-lowered' : ''} ${settings.highContrast ? 'is-contrast' : ''}`}
    data-log-target="screen-position-pad" aria-label={settings.lowScreen ? '화면 위로 올리기' : '화면 아래로 내리기'} onClick={toggleScreenHeight}>
    <span>{settings.lowScreen ? '화면 위로 올리기' : '화면 아래로 내리기'}<span className="screen-position-arrow" aria-hidden="true">{settings.lowScreen ? '⌃' : '⌄'}</span></span>
  </button><div ref={touchLog.root} className={`kiosk ${settings.largeText ? 'large-text' : ''} ${settings.largeButton ? 'large-button' : ''} ${settings.simpleScreen ? 'simple-screen' : ''} ${settings.lowScreen ? 'low-screen' : ''} ${settings.highContrast ? 'high-contrast' : ''}`}>
    <header className="header">
      <div className="kiosk-identity"><div><a data-log-target="menu-home" className="brand" href="#" onClick={event => { event.preventDefault(); if (screen !== 'complete') setScreen('menu'); }}>온기 카페</a><span className="sample-badge">{sampleMode ? '개발용 샘플' : '샘플 주문'} · 실제 결제 없음</span></div><KioskClock /></div>
      <div className="kiosk-toolbar"><KioskModeBar settings={settings} voiceEnabled={voice.enabled}
        voiceReady={screen === 'menu' && (state.status === 'ready' || state.status === 'saving') && !!state.session && !state.order && voice.supported}
        onStandard={useStandardMode} onSetting={key => { setSettings(current => ({ ...current, [key]: !current[key] })); }}
        onVoice={() => voiceController.setEnabled(!voice.enabled)} />
        <button data-log-target="support-toggle" className="support-trigger" aria-expanded={supportOpen} aria-controls="support-panel" onClick={() => setSupportOpen(!supportOpen)}>화면 도움 {supportOpen ? '닫기' : '열기'}</button>
      </div>
    </header>
    <section id="support-panel" className="support-panel" hidden={!supportOpen} aria-label="화면 도움 설정">
      <div><h2>편한 화면으로 주문해 주세요</h2><p>설정을 바꿔도 담은 메뉴는 그대로예요.</p></div>
      <div className="support-options">
        {(Object.keys(supportLabels) as (keyof Settings)[]).map(key => <button data-log-target={`support:${key}`} key={key} aria-pressed={settings[key]} onClick={() => setSettings(current => ({ ...current, [key]: !current[key] }))}>{settings[key] ? '✓ ' : ''}{supportLabels[key]}</button>)}
        {import.meta.env.DEV && <button data-log-target="support:combinedEnlargement" aria-pressed={combinedEnlargement} onClick={toggleCombinedEnlargement}>{combinedEnlargement ? '✓ ' : ''}큰 글씨 + 큰 버튼</button>}
        <button data-log-target="support-reset" onClick={() => setSettings({ ...initialSettings })}>기본 화면</button>
      </div>
      <ReadAloudControls root={touchLog.root} voiceController={voiceController} screenKey={`${state.session?.session_id}:${screen}:${selected?.product_id ?? ''}:${restartOpen}`} />
    </section>
    <main>
      {!selected && feedback}
      <div className="cart-notice" role="status" aria-live="polite" hidden={!state.notice || screen !== 'menu'}>{state.notice}<button data-log-target="notice-close" aria-label="안내 닫기" onClick={() => controller.clearNotice()}>✕</button></div>
      <nav className="steps" aria-label="주문 단계">{['메뉴 선택', '주문 확인', '주문 완료'].map((label, index) => <span key={label} aria-current={index === ['menu', 'review', 'complete'].indexOf(screen) ? 'step' : undefined}><b>{index + 1}</b> {label}</span>)}</nav>
      {storageWarning && <p role="alert">화면 설정을 기억하지 못했어요. 새로고침하면 기본 화면으로 돌아갈 수 있어요.</p>}
      {settings.stepGuide && <div className="guide" role="status">{screen === 'menu' ? <><p>① 메뉴를 골라 옵션과 수량을 정해 주세요.</p><p>② 담은 뒤 화면 아래에서 주문을 확인해 주세요.</p></> : screen === 'review' ? <><p>① 담은 메뉴와 수량을 확인해 주세요.</p><p>② 화면 아래에서 샘플 주문을 완료해 주세요.</p></> : <p>주문번호를 확인한 뒤 새 주문을 시작해 주세요.</p>}</div>}
      {screen === 'complete' ? <section className="complete"><h1 ref={heading} tabIndex={-1}>샘플 주문이 끝났어요</h1><p>샘플 주문번호</p><strong className="order-number">{orderNumber}</strong><p>실제 결제나 매장 주문은 진행되지 않았어요.</p></section> : <>
        <section className="intro"><h1 ref={heading} tabIndex={-1}>{screen === 'menu' ? '메뉴를 골라 주세요' : '담은 메뉴를 확인해 주세요'}</h1></section>
      {screen === 'menu' && <VoiceModeToggle controller={voiceController} ready={(state.status === 'ready' || state.status === 'saving') && state.session !== null && state.order === null} sampleMode={sampleMode} />}
        <div className="order-layout"><section className="menu-section" aria-label={screen === 'menu' ? '상품 목록' : '주문 내역'}>
          {screen === 'menu' ? <><div className="categories" aria-label="상품 분류">{(['all', 'coffee', 'drink', 'food'] as const).map(value => <button data-log-target={`category:${value === 'all' ? '전체' : categoryLabels[value]}`} key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>{value === 'all' ? '전체' : categoryLabels[value]}</button>)}</div><div className="product-grid">
            {state.products.filter(product => category === 'all' || product.category === category).map(product => <button data-log-target={`product:${product.product_id}`} className="product" key={product.product_id} disabled={writeDisabled || !product.available} onClick={event => { opener.current = event.currentTarget; setSelected(product); setTemperature(product.temperatures[0] ?? null); setQuantity(1); }}>
              <span className="product-info"><strong>{product.name}</strong><span className="product-identity"><span className="product-mark" aria-hidden="true"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{product.category === 'food' ? <><path d="m3 12 3-6h12l3 6-3 6H6Z" /><path d="m8 7 2 4m4-4 2 4" /></> : <><path d="M5 8h12v6a5 5 0 0 1-5 5h-2a5 5 0 0 1-5-5ZM17 9h2a3 3 0 0 1 0 6h-2M4 22h16M8 2v2m4-2v2" /></>}</svg></span><span className="product-category">{categoryLabels[product.category]}</span></span><span className="description">{product.description}</span><span className="product-price">{money(product.unit_price)}</span>{!product.available && <span>품절</span>}</span>
            </button>)}
          </div></> : <section className="review-card"><h2>주문 내역</h2>{count ? <ul>{cartRows}</ul> : <p>아직 담은 메뉴가 없어요. 메뉴를 먼저 골라 주세요.</p>}<button data-log-target="review-back" className="secondary" onClick={() => setScreen('menu')}>← 메뉴 더 고르기</button></section>}
        </section><aside className="cart"><div className="cart-heading"><h2>{screen === 'menu' ? '담은 메뉴' : '주문 요약'}</h2><span>{count}개</span></div>{screen === 'menu' ? (count ? <ul>{cartRows}</ul> : <div className="empty-cart"><span aria-hidden="true">＋</span><p>메뉴를 담아 주세요</p><span>선택한 메뉴가 여기에 보여요.</span></div>) : <p className="cart-summary">담은 메뉴 {count}개를 확인해 주세요.<br />실제 결제는 진행되지 않아요.</p>}</aside></div>
      </>}
    </main><footer className="footer"><span>온기 카페</span><span>천천히 골라도 괜찮아요.</span></footer>
    <section ref={actionsRef} className="order-actions" aria-label="주문 진행"><div className="order-actions-inner">
      {screen === 'complete' ? <div className="order-actions-summary"><p>실제 결제 없음 · 샘플 주문이에요.</p>{screenHeightButton}</div> : <div><div className="order-actions-summary"><div className="total"><span>총 주문 금액 · {count}개</span><strong>{money(sum)}</strong></div>{screenHeightButton}</div><p>샘플 주문 · 실제 결제 없음</p></div>}
      {screen !== 'complete' && <button ref={restartTrigger} data-log-target="order-restart" className="order-restart" disabled={busy || state.status === 'uncertain'} onClick={() => { voiceController.setEnabled(false); setRestartOpen(true); }}>처음으로</button>}
      <button data-log-target={screen === 'complete' ? 'new-order' : screen === 'menu' ? 'review-open' : 'simulate-payment'} className="primary order-confirm" disabled={screen === 'complete' ? busy : !count || writeDisabled} onClick={() => screen === 'complete' ? void startNewOrder() : screen === 'menu' ? openReview() : void controller.checkout()}>{screen === 'complete' ? '새 주문 시작' : screen === 'menu' ? '주문 확인' : '샘플 주문 완료'}</button>
    </div></section>
    <dialog ref={dialog} className="options-dialog" onCancel={event => { event.preventDefault(); closeOptions(); }} onClick={event => { if (event.target === event.currentTarget) closeOptions(); }} aria-labelledby="option-title">
      {selected && <><div className="dialog-heading"><h2 id="option-title">{selected.name}</h2><button data-log-target="options-close" aria-label="옵션 창 닫기" onClick={closeOptions}>✕</button></div><p>{selected.temperatures.length ? '원하는 옵션을 골라 주세요.' : '원하는 수량을 골라 주세요.'}</p>{feedback}
        {selected.temperatures.length > 0 && <fieldset><legend>온도</legend><div className="option-buttons">{selected.temperatures.map(option => <button data-log-target={`temperature:${temperatureLabel(option)}`} key={option} aria-pressed={temperature === option} disabled={writeDisabled} onClick={() => { setTemperature(option); setQuantity(1); }}>{temperatureLabel(option)}</button>)}</div></fieldset>}
        <div className="dialog-quantity"><span>수량 (최대 {MAX_QUANTITY}개)</span><div className="quantity"><button data-log-target="options-decrease" disabled={writeDisabled || quantity === 1} aria-label="선택 수량 줄이기" onClick={() => setQuantity(quantity - 1)}>−</button><span>{quantity}</span><button data-log-target="options-increase" disabled={writeDisabled || quantity >= remaining} aria-label="선택 수량 늘리기" onClick={() => setQuantity(quantity + 1)}>+</button></div></div>
        {remaining <= 0 && <p role="status">이 메뉴와 온도는 이미 최대 수량을 담았어요.</p>}
        <button data-log-target="cart-add" className="primary" disabled={writeDisabled || quantity > remaining} onClick={() => void addSelected()}>{money(selected.unit_price * quantity)} · 담기</button>
      </>}
    </dialog>
    <dialog ref={restartDialog} className="options-dialog" aria-labelledby="restart-title" onCancel={event => { event.preventDefault(); closeRestart(); }}>
      <h2 id="restart-title">처음부터 주문할까요?</h2>
      <p>담은 메뉴를 비우고 새 주문을 시작합니다. 화면 도움 설정은 유지합니다.</p>
      <div className="order-feedback-actions"><button data-log-target="order-restart-cancel" onClick={closeRestart}>계속 주문하기</button>
        <button data-log-target="order-restart-confirm" disabled={busy || state.status === 'uncertain'} onClick={() => { setRestartOpen(false); void startNewOrder(true); }}>처음부터 주문하기</button></div>
    </dialog>
  </div><TouchLogPanel /></>;
}
