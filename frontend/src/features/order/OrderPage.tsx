import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { backendApi } from '../../shared/api/index.ts';
import type { Product, ProductCategory, Temperature } from '../../shared/api/index.ts';
import { categoryLabels, initialSettings, MAX_QUANTITY, money, productIcon, readSettings, settingsStorageKey, temperatureLabel } from './model.ts';
import type { Settings } from './model.ts';
import { OrderController } from './orderController.ts';
import { orderCopy } from './copy.ts';
import { createSampleOrderApi } from './sampleOrderApi.ts';
import { useTouchLog } from './useTouchLog.ts';
import { TouchLogPanel } from './TouchLogPanel.tsx';
import './order.css';

const supportLabels: Record<keyof Settings, string> = { largeText: '큰 글씨', largeButton: '큰 버튼', simpleScreen: '간편 화면', stepGuide: '단계별 안내' };
const sampleMode = import.meta.env.DEV && import.meta.env.VITE_ORDER_SAMPLE === 'true';

export function OrderPage() {
  const [controller] = useState(() => new OrderController(sampleMode ? createSampleOrderApi() : backendApi));
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
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
  const heading = useRef<HTMLHeadingElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const touchLog = useTouchLog(screen, category === 'all' ? '전체' : categoryLabels[category], selected?.product_id ?? null, settings, state.session?.session_id ?? null);
  useEffect(() => { void controller.initialize(); }, [controller]);
  useEffect(() => { try { localStorage.setItem(settingsStorageKey, JSON.stringify(settings)); } catch { setStorageWarning(true); } }, [settings]);
  useEffect(() => { heading.current?.focus(); }, [screen]);
  useEffect(() => { if (selected) dialog.current?.showModal(); else if (dialog.current?.open) dialog.current.close(); }, [selected]);
  useEffect(() => {
    if (state.order) { setOrderNumber(state.order.order_number); setScreen('complete'); }
  }, [state.order]);

  const busy = state.status === 'loading' || state.status === 'saving';
  const writeDisabled = state.status !== 'ready' || state.order !== null;
  const count = state.cart?.total_quantity ?? 0;
  const sum = state.cart?.total_amount ?? 0;
  const remaining = MAX_QUANTITY - (state.cart?.items.find(item => item.product_id === selected?.product_id && item.temperature === temperature)?.quantity ?? 0);
  function closeOptions() { setSelected(null); opener.current?.focus(); }
  async function addSelected() {
    if (!selected) return;
    if (await controller.addItem({ product_id: selected.product_id, temperature, quantity })) closeOptions();
  }
  async function retry() {
    if (await controller.retry()) closeOptions();
  }
  async function startNewOrder() {
    closeOptions();
    setScreen('menu'); setOrderNumber(''); setCategory('all');
    await controller.startNewOrder();
  }
  async function restartAfterUncertain() {
    if (!controller.abandonPending()) return;
    setScreen('menu'); setOrderNumber(''); setCategory('all');
    await startNewOrder();
  }
  const feedback = <>{busy && <p className="order-progress" role="status">{state.status === 'loading' ? orderCopy.preparing : orderCopy.saving}</p>}
    {state.message && <div className="order-feedback" role="alert"><p>{state.message}</p>
      {state.status === 'uncertain' && <>
        {state.canAbandonPending && <p>{orderCopy.abandonWarning}</p>}
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

  return <><div ref={touchLog.root} className={`kiosk ${settings.largeText ? 'large-text' : ''} ${settings.largeButton ? 'large-button' : ''} ${settings.simpleScreen ? 'simple-screen' : ''}`}>
    <header className="header"><a data-log-target="menu-home" className="brand" href="#" onClick={event => { event.preventDefault(); if (screen !== 'complete') setScreen('menu'); }}>온기 카페</a><span className="sample-badge">{sampleMode ? '개발용 샘플' : '샘플 주문'} · 실제 결제 없음</span><button data-log-target="support-toggle" className="support-trigger" aria-expanded={supportOpen} aria-controls="support-panel" onClick={() => setSupportOpen(!supportOpen)}>화면 도움 {supportOpen ? '닫기' : '열기'}</button></header>
    {supportOpen && <section id="support-panel" className="support-panel" aria-label="화면 도움 설정"><div><h2>편한 화면으로 주문해 주세요</h2><p>설정을 바꿔도 담은 메뉴는 그대로예요.</p></div><div className="support-options">{(Object.keys(supportLabels) as (keyof Settings)[]).map(key => <button data-log-target={`support:${key}`} key={key} aria-pressed={settings[key]} onClick={() => setSettings(current => ({ ...current, [key]: !current[key] }))}>{settings[key] ? '✓ ' : ''}{supportLabels[key]}</button>)}<button data-log-target="support-reset" onClick={() => setSettings({ ...initialSettings })}>기본 화면</button></div></section>}
    <main>
      {!selected && feedback}
      <div className="cart-notice" role="status" aria-live="polite" hidden={!state.notice || screen !== 'menu'}>{state.notice}<button data-log-target="notice-close" aria-label="안내 닫기" onClick={() => controller.clearNotice()}>✕</button></div>
      <nav className="steps" aria-label="주문 단계">{['메뉴 선택', '주문 확인', '주문 완료'].map((label, index) => <span key={label} aria-current={index === ['menu', 'review', 'complete'].indexOf(screen) ? 'step' : undefined}><b>0{index + 1}</b> {label}</span>)}</nav>
      {storageWarning && <p role="alert">화면 설정을 기억하지 못했어요. 새로고침하면 기본 화면으로 돌아갈 수 있어요.</p>}
      {settings.stepGuide && <div className="guide" role="status">{screen === 'menu' ? <><p>① 메뉴를 골라 옵션과 수량을 정해 주세요.</p><p>② 담은 뒤 화면 아래에서 주문을 확인해 주세요.</p></> : screen === 'review' ? <><p>① 담은 메뉴와 수량을 확인해 주세요.</p><p>② 화면 아래에서 샘플 주문을 완료해 주세요.</p></> : <p>주문번호를 확인한 뒤 새 주문을 시작해 주세요.</p>}</div>}
      {screen === 'complete' ? <section className="complete"><h1 ref={heading} tabIndex={-1}>샘플 주문이 끝났어요</h1><p>샘플 주문번호</p><strong className="order-number">{orderNumber}</strong><p>실제 결제나 매장 주문은 진행되지 않았어요.</p></section> : <>
        <section className="intro"><h1 ref={heading} tabIndex={-1}>{screen === 'menu' ? '메뉴를 골라 주세요' : '담은 메뉴를 확인해 주세요'}</h1><p>{screen === 'menu' ? '메뉴를 누르면 옵션과 수량을 고를 수 있어요.' : '옵션과 수량을 확인한 뒤 샘플 주문을 완료해 주세요.'}</p></section>
        <div className="order-layout"><section className="menu-section" aria-label={screen === 'menu' ? '상품 목록' : '주문 내역'}>
          {screen === 'menu' ? <><div className="categories" aria-label="상품 분류">{(['all', 'coffee', 'drink', 'food'] as const).map(value => <button data-log-target={`category:${value === 'all' ? '전체' : categoryLabels[value]}`} key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>{value === 'all' ? '전체' : categoryLabels[value]}</button>)}</div><div className="product-grid">
            {state.products.filter(product => category === 'all' || product.category === category).map(product => <button data-log-target={`product:${product.product_id}`} className="product" key={product.product_id} disabled={writeDisabled || !product.available} onClick={event => { opener.current = event.currentTarget; setSelected(product); setTemperature(product.temperatures[0] ?? null); setQuantity(1); }}>
              <span className={`product-art art-${categoryLabels[product.category]}`} aria-hidden="true">{productIcon(product.product_id, product.category)}</span><span className="product-info"><span className="product-category">{categoryLabels[product.category]}</span><strong>{product.name}</strong><span className="description">{product.description}</span><span className="product-price">{money(product.unit_price)}<span aria-hidden="true">＋</span></span>{!product.available && <span>품절</span>}</span>
            </button>)}
          </div></> : <section className="review-card"><h2>주문 내역</h2>{count ? <ul>{cartRows}</ul> : <p>아직 담은 메뉴가 없어요. 메뉴를 먼저 골라 주세요.</p>}<button data-log-target="review-back" className="secondary" onClick={() => setScreen('menu')}>← 메뉴 더 고르기</button></section>}
        </section><aside className="cart"><div className="cart-heading"><h2>{screen === 'menu' ? '담은 메뉴' : '주문 요약'}</h2><span>{count}개</span></div>{screen === 'menu' ? (count ? <ul>{cartRows}</ul> : <div className="empty-cart"><span aria-hidden="true">＋</span><p>메뉴를 담아 주세요</p><span>선택한 메뉴가 여기에 보여요.</span></div>) : <p className="cart-summary">담은 메뉴 {count}개를 확인해 주세요.<br />실제 결제는 진행되지 않아요.</p>}</aside></div>
      </>}
    </main><footer className="footer"><span>온기 카페</span><span>천천히 골라도 괜찮아요.</span></footer>
    <section className="order-actions" aria-label="주문 진행"><div className="order-actions-inner">
      {screen === 'complete' ? <p>실제 결제 없음 · 샘플 주문이에요.</p> : <div><div className="total"><span>총 주문 금액 · {count}개</span><strong>{money(sum)}</strong></div><p>{screen === 'menu' ? '담은 메뉴를 다음 화면에서 확인할 수 있어요.' : '실제 결제 없이 샘플 주문을 완료해요.'}</p></div>}
      <button data-log-target={screen === 'complete' ? 'new-order' : screen === 'menu' ? 'review-open' : 'simulate-payment'} className="primary order-confirm" disabled={screen === 'complete' ? busy : !count || writeDisabled} onClick={() => screen === 'complete' ? void startNewOrder() : screen === 'menu' ? setScreen('review') : void controller.checkout()}>{screen === 'complete' ? '새 주문 시작' : screen === 'menu' ? '주문 확인' : '샘플 주문 완료'} <span aria-hidden="true">→</span></button>
    </div></section>
    <dialog ref={dialog} className="options-dialog" onCancel={event => { event.preventDefault(); closeOptions(); }} onClick={event => { if (event.target === event.currentTarget) closeOptions(); }} aria-labelledby="option-title">
      {selected && <><div className="dialog-heading"><h2 id="option-title">{selected.name}</h2><button data-log-target="options-close" aria-label="옵션 창 닫기" onClick={closeOptions}>✕</button></div><p>{selected.temperatures.length ? '원하는 옵션을 골라 주세요.' : '원하는 수량을 골라 주세요.'}</p>{feedback}
        {selected.temperatures.length > 0 && <fieldset><legend>온도</legend><div className="option-buttons">{selected.temperatures.map(option => <button data-log-target={`temperature:${temperatureLabel(option)}`} key={option} aria-pressed={temperature === option} disabled={writeDisabled} onClick={() => { setTemperature(option); setQuantity(1); }}>{temperatureLabel(option)}</button>)}</div></fieldset>}
        <div className="dialog-quantity"><span>수량 (최대 {MAX_QUANTITY}개)</span><div className="quantity"><button data-log-target="options-decrease" disabled={writeDisabled || quantity === 1} aria-label="선택 수량 줄이기" onClick={() => setQuantity(quantity - 1)}>−</button><span>{quantity}</span><button data-log-target="options-increase" disabled={writeDisabled || quantity >= remaining} aria-label="선택 수량 늘리기" onClick={() => setQuantity(quantity + 1)}>+</button></div></div>
        {remaining <= 0 && <p role="status">이 메뉴와 온도는 이미 최대 수량을 담았어요.</p>}
        <button data-log-target="cart-add" className="primary" disabled={writeDisabled || quantity > remaining} onClick={() => void addSelected()}>{money(selected.unit_price * quantity)} · 담기</button>
      </>}
    </dialog>
  </div><TouchLogPanel /></>;
}
