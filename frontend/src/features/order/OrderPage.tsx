import { useEffect, useRef, useState } from 'react';
import { addItem, initialState, money, products, readState, storageKey, total } from './model.ts';
import type { Product, Settings } from './model.ts';
import './order.css';

const supportLabels: Record<keyof Settings, string> = { largeText: '큰 글씨', largeButton: '큰 버튼', simpleScreen: '간편 화면', stepGuide: '단계별 안내' };
export function OrderPage() {
  const [state, setState] = useState(() => { try { return readState(localStorage.getItem(storageKey)); } catch { return initialState; } });
  const [screen, setScreen] = useState<'menu' | 'review' | 'complete'>('menu');
  const [category, setCategory] = useState('전체');
  const [selected, setSelected] = useState<Product | null>(null);
  const [temperature, setTemperature] = useState('아이스');
  const [quantity, setQuantity] = useState(1);
  const [supportOpen, setSupportOpen] = useState(false);
  const [notice, setNotice] = useState('');
  const [storageWarning, setStorageWarning] = useState(false);
  const [orderNumber, setOrderNumber] = useState('');
  const heading = useRef<HTMLHeadingElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  useEffect(() => { try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch { setStorageWarning(true); } }, [state]);
  useEffect(() => { heading.current?.focus(); }, [screen]);
  useEffect(() => { if (selected) dialog.current?.showModal(); else if (dialog.current?.open) dialog.current.close(); }, [selected]);
  const count = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  const sum = total(state.cart);
  function closeOptions() { setSelected(null); opener.current?.focus(); }
  function finish() {
    if (!state.cart.length) return;
    setOrderNumber(String(Math.floor(Math.random() * 900) + 100));
    setState(current => ({ ...current, cart: [] }));
    setScreen('complete');
  }
  function changeQuantity(index: number, amount: number) {
    setState(current => ({ ...current, cart: current.cart.map((item, i) => i === index ? { ...item, quantity: Math.max(1, Math.min(20, item.quantity + amount)) } : item) }));
  }
  const cartRows = state.cart.map((item, index) => {
    const product = products.find(p => p.id === item.productId)!;
    return <li key={`${item.productId}-${item.temperature}`} className="cart-row">
      <div><strong>{product.name}</strong><span>{product.temperatures.length > 1 ? `${item.temperature} · ` : ''}{money(product.price)}</span></div>
      <div className="cart-controls"><div className="quantity"><button aria-label={`${product.name} ${item.temperature} 수량 줄이기`} disabled={item.quantity === 1} onClick={() => changeQuantity(index, -1)}>−</button><span>{item.quantity}</span><button aria-label={`${product.name} ${item.temperature} 수량 늘리기`} disabled={item.quantity === 20} onClick={() => changeQuantity(index, 1)}>+</button></div><button className="text-button" aria-label={`${product.name} ${item.temperature} 삭제`} onClick={() => setState(current => ({ ...current, cart: current.cart.filter((_, i) => i !== index) }))}>삭제</button></div>
    </li>;
  });
  return <div className={`kiosk ${state.settings.largeText ? 'large-text' : ''} ${state.settings.largeButton ? 'large-button' : ''} ${state.settings.simpleScreen ? 'simple-screen' : ''}`}>
    <header className="header"><a className="brand" href="#" onClick={event => { event.preventDefault(); setScreen('menu'); }}>온기<span>ONGI COFFEE</span></a><span className="sample-badge">샘플 주문 · 실제 결제 없음</span><button className="support-trigger" aria-expanded={supportOpen} aria-controls="support-panel" onClick={() => setSupportOpen(!supportOpen)}>화면 도움 {supportOpen ? '닫기' : '열기'}</button></header>
    {supportOpen && <section id="support-panel" className="support-panel" aria-label="화면 도움 설정"><div><h2>편한 화면으로 주문하세요</h2><p>설정을 바꿔도 담은 메뉴는 그대로 유지됩니다.</p></div><div className="support-options">{(Object.keys(supportLabels) as (keyof Settings)[]).map(key => <button key={key} aria-pressed={state.settings[key]} onClick={() => setState(current => ({ ...current, settings: { ...current.settings, [key]: !current.settings[key] } }))}>{state.settings[key] ? '✓ ' : ''}{supportLabels[key]}</button>)}<button onClick={() => setState(current => ({ ...current, settings: { ...initialState.settings } }))}>기본 화면</button></div></section>}
    <main>
      <div className="cart-notice" role="status" aria-live="polite" hidden={!notice || screen !== 'menu'}>{notice}<button aria-label="담기 완료 안내 닫기" onClick={() => setNotice('')}>✕</button></div>
      <nav className="steps" aria-label="주문 단계">{['메뉴 선택', '주문 확인', '주문 완료'].map((label, index) => <span key={label} aria-current={index === ['menu', 'review', 'complete'].indexOf(screen) ? 'step' : undefined}><b>0{index + 1}</b> {label}</span>)}</nav>
      {storageWarning && <p role="alert">이 브라우저에서는 저장이 제한되어 새로고침하면 주문이 사라질 수 있습니다.</p>}
      {state.settings.stepGuide && <p className="guide" role="status">{screen === 'menu' ? '① 메뉴를 선택하고 옵션을 정한 뒤 담아주세요. ② 오른쪽에서 주문을 확인하세요.' : screen === 'review' ? '메뉴와 수량을 확인한 뒤 모의 결제를 눌러주세요. 메뉴 선택으로 돌아가도 주문은 유지됩니다.' : '주문번호를 확인하세요. 새 주문을 누르면 다시 시작합니다.'}</p>}
      {screen === 'complete' ? <section className="complete"><span className="eyebrow">THANK YOU</span><h1 ref={heading} tabIndex={-1}>주문이 완료되었습니다</h1><p>모의 주문번호</p><strong className="order-number">{orderNumber}</strong><p>실제 결제나 매장 주문은 진행되지 않았습니다.</p><button className="primary" onClick={() => { setScreen('menu'); setNotice(''); }}>새 주문 시작</button></section> : <>
      <section className="intro"><span className="eyebrow">A LITTLE MOMENT OF WARMTH</span><h1 ref={heading} tabIndex={-1}>{screen === 'menu' ? '오늘은 무엇을 드실까요?' : '담은 메뉴를 확인해주세요'}</h1><p>{screen === 'menu' ? '취향에 맞는 한 잔, 편안하게 골라보세요.' : '옵션과 수량을 확인한 뒤 주문을 마무리하세요.'}</p></section>
      <div className="order-layout"><section className="menu-section" aria-label={screen === 'menu' ? '상품 목록' : '주문 내역'}>
      {screen === 'menu' ? <><div className="categories" aria-label="상품 분류">{['전체', '커피', '음료', '푸드'].map(label => <button key={label} aria-pressed={category === label} onClick={() => setCategory(label)}>{label}</button>)}</div><div className="product-grid">{products.filter(product => category === '전체' || product.category === category).map(product => <button className="product" key={product.id} onClick={event => { opener.current = event.currentTarget; setSelected(product); setTemperature(product.temperatures[0]); setQuantity(1); }}><span className={`product-art art-${product.category}`} aria-hidden="true">{product.icon}</span><span className="product-info"><span className="product-category">{product.category}</span><strong>{product.name}</strong><span className="description">{product.description}</span><span className="product-price">{money(product.price)}<span aria-hidden="true">＋</span></span></span></button>)}</div></> : <section className="review-card"><h2>주문 내역</h2>{count ? <ul>{cartRows}</ul> : <p>담은 메뉴가 없습니다. 메뉴를 먼저 선택해주세요.</p>}<button className="secondary" onClick={() => setScreen('menu')}>← 메뉴 더 고르기</button></section>}
      </section><aside className="cart"><div className="cart-heading"><h2>{screen === 'menu' ? '담은 메뉴' : '결제 금액'}</h2><span>{count}개</span></div>{screen === 'menu' && (count ? <ul>{cartRows}</ul> : <div className="empty-cart"><span aria-hidden="true">＋</span><p>메뉴를 담아주세요</p><span>선택한 메뉴가 여기에 표시됩니다.</span></div>)}<div className="cart-footer"><div className="total"><span>총 주문 금액</span><strong>{money(sum)}</strong></div><button className="primary" disabled={!count} onClick={() => screen === 'menu' ? setScreen('review') : finish()}>{screen === 'menu' ? '주문 확인' : '모의 결제하기'} <span aria-hidden="true">→</span></button><p>{screen === 'menu' ? '다음 화면에서 주문을 다시 확인할 수 있어요.' : '샘플 주문이며 실제로 결제되지 않습니다.'}</p></div></aside></div></>}
    </main><footer className="footer"><span>온기 카페</span><span>천천히 골라도 괜찮아요.</span></footer>
    <dialog ref={dialog} className="options-dialog" onCancel={event => { event.preventDefault(); closeOptions(); }} onClick={event => { if (event.target === event.currentTarget) closeOptions(); }} aria-labelledby="option-title">{selected && <><div className="dialog-heading"><h2 id="option-title">{selected.name}</h2><button aria-label="옵션 창 닫기" onClick={closeOptions}>✕</button></div><p>{selected.temperatures.length > 1 ? '원하는 옵션을 선택해주세요.' : '원하는 수량을 선택해주세요.'}</p>{selected.temperatures.length > 1 && <fieldset><legend>온도</legend><div className="option-buttons">{selected.temperatures.map(option => <button key={option} aria-pressed={temperature === option} onClick={() => setTemperature(option)}>{option}</button>)}</div></fieldset>}<div className="dialog-quantity"><span>수량 (최대 20개)</span><div className="quantity"><button disabled={quantity === 1} aria-label="선택 수량 줄이기" onClick={() => setQuantity(quantity - 1)}>−</button><span>{quantity}</span><button disabled={quantity === 20} aria-label="선택 수량 늘리기" onClick={() => setQuantity(quantity + 1)}>+</button></div></div><button className="primary" onClick={() => { setState(current => ({ ...current, cart: addItem(current.cart, { productId: selected.id, temperature, quantity }) })); setNotice(`${selected.name}${selected.temperatures.length > 1 ? ` ${temperature}` : ''} 메뉴를 담았습니다.`); closeOptions(); }}>{money(selected.price * quantity)} · 담기</button></>}</dialog>
  </div>;
}
