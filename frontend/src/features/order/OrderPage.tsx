import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { backendApi } from '../../shared/api/index.ts';
import type { Product, ProductCategory, Temperature } from '../../shared/api/index.ts';
import { categoryLabels, initialSettings, MAX_QUANTITY, money, productIcon, readSettings, settingsStorageKey, temperatureLabel } from './model.ts';
import type { Settings } from './model.ts';
import { OrderController } from './orderController.ts';
import { useTouchLog } from './useTouchLog.ts';
import { TouchLogPanel } from './TouchLogPanel.tsx';
import './order.css';

const supportLabels: Record<keyof Settings, string> = { largeText: '큰 글씨', largeButton: '큰 버튼', simpleScreen: '간편 화면', stepGuide: '단계별 안내' };

export function OrderPage() {
  const [controller] = useState(() => new OrderController(backendApi));
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
  const touchLog = useTouchLog(screen, category === 'all' ? '전체' : categoryLabels[category], selected?.product_id ?? null, settings);
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
    if (await controller.startNewOrder()) {
      touchLog.startNewSession();
      setScreen('menu'); setOrderNumber(''); setCategory('all');
    }
  }
  const feedback = <>{busy && <p className="order-progress" role="status">{state.status === 'loading' ? '주문을 준비하고 있습니다.' : '요청을 처리하고 있습니다.'}</p>}
    {state.message && <div className="order-feedback" role="alert"><p>{state.message}</p>
      {state.status === 'uncertain' && <button data-log-target="order-result-retry" disabled={Date.now() < state.retryAt} onClick={() => void retry()}>결과 다시 확인</button>}
      {state.status === 'disconnected' && <button data-log-target="order-connect-retry" onClick={() => screen === 'complete' ? void startNewOrder() : void controller.initialize()}>다시 연결</button>}
      {state.status === 'ended' && <button data-log-target="order-session-restart" onClick={() => void startNewOrder()}>새 이용 시작</button>}
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
    <header className="header"><a data-log-target="menu-home" className="brand" href="#" onClick={event => { event.preventDefault(); if (screen !== 'complete') setScreen('menu'); }}>온기<span>ONGI COFFEE</span></a><span className="sample-badge">샘플 주문 · 실제 결제 없음</span><button data-log-target="support-toggle" className="support-trigger" aria-expanded={supportOpen} aria-controls="support-panel" onClick={() => setSupportOpen(!supportOpen)}>화면 도움 {supportOpen ? '닫기' : '열기'}</button></header>
    {supportOpen && <section id="support-panel" className="support-panel" aria-label="화면 도움 설정"><div><h2>편한 화면으로 주문하세요</h2><p>설정을 바꿔도 담은 메뉴는 그대로 유지됩니다.</p></div><div className="support-options">{(Object.keys(supportLabels) as (keyof Settings)[]).map(key => <button data-log-target={`support:${key}`} key={key} aria-pressed={settings[key]} onClick={() => setSettings(current => ({ ...current, [key]: !current[key] }))}>{settings[key] ? '✓ ' : ''}{supportLabels[key]}</button>)}<button data-log-target="support-reset" onClick={() => setSettings({ ...initialSettings })}>기본 화면</button></div></section>}
    <main>
      {!selected && feedback}
      <div className="cart-notice" role="status" aria-live="polite" hidden={!state.notice || screen !== 'menu'}>{state.notice}<button data-log-target="notice-close" aria-label="안내 닫기" onClick={() => controller.clearNotice()}>✕</button></div>
      <nav className="steps" aria-label="주문 단계">{['메뉴 선택', '주문 확인', '주문 완료'].map((label, index) => <span key={label} aria-current={index === ['menu', 'review', 'complete'].indexOf(screen) ? 'step' : undefined}><b>0{index + 1}</b> {label}</span>)}</nav>
      {storageWarning && <p role="alert">화면 도움 설정을 저장하지 못했습니다. 새로고침하면 기본 설정으로 돌아갈 수 있습니다.</p>}
      {settings.stepGuide && <p className="guide" role="status">{screen === 'menu' ? '① 메뉴를 선택하고 옵션을 정한 뒤 담아주세요. ② 오른쪽에서 주문을 확인하세요.' : screen === 'review' ? '메뉴와 수량을 확인한 뒤 모의 결제를 눌러주세요. 메뉴 선택으로 돌아가도 주문은 유지됩니다.' : '주문번호를 확인하세요. 새 주문을 누르면 다시 시작합니다.'}</p>}
      {screen === 'complete' ? <section className="complete"><span className="eyebrow">THANK YOU</span><h1 ref={heading} tabIndex={-1}>주문이 완료되었습니다</h1><p>모의 주문번호</p><strong className="order-number">{orderNumber}</strong><p>실제 결제나 매장 주문은 진행되지 않았습니다.</p><button data-log-target="new-order" className="primary" disabled={busy} onClick={() => void startNewOrder()}>새 주문 시작</button></section> : <>
        <section className="intro"><span className="eyebrow">A LITTLE MOMENT OF WARMTH</span><h1 ref={heading} tabIndex={-1}>{screen === 'menu' ? '오늘은 무엇을 드실까요?' : '담은 메뉴를 확인해주세요'}</h1><p>{screen === 'menu' ? '취향에 맞는 한 잔, 편안하게 골라보세요.' : '옵션과 수량을 확인한 뒤 주문을 마무리하세요.'}</p></section>
        <div className="order-layout"><section className="menu-section" aria-label={screen === 'menu' ? '상품 목록' : '주문 내역'}>
          {screen === 'menu' ? <><div className="categories" aria-label="상품 분류">{(['all', 'coffee', 'drink', 'food'] as const).map(value => <button data-log-target={`category:${value === 'all' ? '전체' : categoryLabels[value]}`} key={value} aria-pressed={category === value} onClick={() => setCategory(value)}>{value === 'all' ? '전체' : categoryLabels[value]}</button>)}</div><div className="product-grid">
            {state.products.filter(product => category === 'all' || product.category === category).map(product => <button data-log-target={`product:${product.product_id}`} className="product" key={product.product_id} disabled={writeDisabled || !product.available} onClick={event => { opener.current = event.currentTarget; setSelected(product); setTemperature(product.temperatures[0] ?? null); setQuantity(1); }}>
              <span className={`product-art art-${categoryLabels[product.category]}`} aria-hidden="true">{productIcon(product.product_id, product.category)}</span><span className="product-info"><span className="product-category">{categoryLabels[product.category]}</span><strong>{product.name}</strong><span className="description">{product.description}</span><span className="product-price">{money(product.unit_price)}<span aria-hidden="true">＋</span></span>{!product.available && <span>품절</span>}</span>
            </button>)}
          </div></> : <section className="review-card"><h2>주문 내역</h2>{count ? <ul>{cartRows}</ul> : <p>담은 메뉴가 없습니다. 메뉴를 먼저 선택해주세요.</p>}<button data-log-target="review-back" className="secondary" onClick={() => setScreen('menu')}>← 메뉴 더 고르기</button></section>}
        </section><aside className="cart"><div className="cart-heading"><h2>{screen === 'menu' ? '담은 메뉴' : '결제 금액'}</h2><span>{count}개</span></div>{screen === 'menu' && (count ? <ul>{cartRows}</ul> : <div className="empty-cart"><span aria-hidden="true">＋</span><p>메뉴를 담아주세요</p><span>선택한 메뉴가 여기에 표시됩니다.</span></div>)}<div className="cart-footer"><div className="total"><span>총 주문 금액</span><strong>{money(sum)}</strong></div><button data-log-target={screen === 'menu' ? 'review-open' : 'simulate-payment'} className={`primary ${screen === 'menu' ? 'order-confirm' : ''}`} disabled={!count || writeDisabled} onClick={() => screen === 'menu' ? setScreen('review') : void controller.checkout()}>{screen === 'menu' ? '주문 확인' : '모의 결제하기'} <span aria-hidden="true">→</span></button><p>{screen === 'menu' ? '다음 화면에서 주문을 다시 확인할 수 있어요.' : '샘플 주문이며 실제로 결제되지 않습니다.'}</p></div></aside></div>
      </>}
    </main><footer className="footer"><span>온기 카페</span><span>천천히 골라도 괜찮아요.</span></footer>
    <dialog ref={dialog} className="options-dialog" onCancel={event => { event.preventDefault(); closeOptions(); }} onClick={event => { if (event.target === event.currentTarget) closeOptions(); }} aria-labelledby="option-title">
      {selected && <><div className="dialog-heading"><h2 id="option-title">{selected.name}</h2><button data-log-target="options-close" aria-label="옵션 창 닫기" onClick={closeOptions}>✕</button></div><p>{selected.temperatures.length ? '원하는 옵션을 선택해주세요.' : '원하는 수량을 선택해주세요.'}</p>{feedback}
        {selected.temperatures.length > 0 && <fieldset><legend>온도</legend><div className="option-buttons">{selected.temperatures.map(option => <button data-log-target={`temperature:${temperatureLabel(option)}`} key={option} aria-pressed={temperature === option} disabled={writeDisabled} onClick={() => { setTemperature(option); setQuantity(1); }}>{temperatureLabel(option)}</button>)}</div></fieldset>}
        <div className="dialog-quantity"><span>수량 (최대 {MAX_QUANTITY}개)</span><div className="quantity"><button data-log-target="options-decrease" disabled={writeDisabled || quantity === 1} aria-label="선택 수량 줄이기" onClick={() => setQuantity(quantity - 1)}>−</button><span>{quantity}</span><button data-log-target="options-increase" disabled={writeDisabled || quantity >= remaining} aria-label="선택 수량 늘리기" onClick={() => setQuantity(quantity + 1)}>+</button></div></div>
        {remaining <= 0 && <p role="status">이 메뉴와 온도는 이미 최대 수량을 담았습니다.</p>}
        <button data-log-target="cart-add" className="primary" disabled={writeDisabled || quantity > remaining} onClick={() => void addSelected()}>{money(selected.unit_price * quantity)} · 담기</button>
      </>}
    </dialog>
  </div><TouchLogPanel /></>;
}
