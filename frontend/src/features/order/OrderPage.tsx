import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { backendApi } from '../../shared/api/index.ts';
import type { CartItem, Product, Temperature } from '../../shared/api/index.ts';
import { categoryLabels, initialSettings, MAX_QUANTITY, readSettings, settingsStorageKey, temperatureLabel } from './model.ts';
import type { Settings } from './model.ts';
import { OrderController } from './orderController.ts';
import { hintCopy, orderCopy, supportCopy } from './copy.ts';
import type { HintKind } from './copy.ts';
import { createSampleOrderApi } from './sampleOrderApi.ts';
import { useTouchLog } from './useTouchLog.ts';
import { captureTouchLogObservation } from './touchLogObservation.ts';
import { TouchLogPanel } from './TouchLogPanel.tsx';
import { VoiceButton, VoicePanel, voiceAutoOffNotice } from './VoiceModeToggle.tsx';
import { ReadAloudControls } from './ReadAloudControls.tsx';
import { createVoiceApi, VoiceController } from '../voice/index.ts';
import './components/tokens.css';
import './order.css';
import './orderAccessibility.css';
import { StepsBar } from './components/StepsBar.tsx';
import { Icon } from './components/icons.tsx';
import { StoreRow } from './components/StoreRow.tsx';
import { ActionBar } from './components/ActionBar.tsx';
import { EntryRow } from './components/EntryRow.tsx';
import { CategoryTabs } from './components/CategoryTabs.tsx';
import type { CategoryFilter } from './components/CategoryTabs.tsx';
import { ProductGrid } from './components/ProductGrid.tsx';
import { MessagePlace } from './components/MessagePlace.tsx';
import { OptionSheet } from './components/OptionSheet.tsx';
import { CartPanel } from './components/CartPanel.tsx';
import { CartSheet } from './components/CartSheet.tsx';
import { ReviewBlock } from './components/ReviewBlock.tsx';
import { DoneBlock } from './components/DoneBlock.tsx';
import { HelpSheet } from './components/HelpSheet.tsx';
import type { CartDisplayLine, CartLineActions } from './components/CartLine.tsx';
import { useNextTouch } from './hook/useNextTouch.ts';
import { briefNoticeMs } from './utils/timing.ts';
import { useSupportDraft, useSupportOffer } from './hook/useSupportOffer.ts';
import { OfferCard } from './components/OfferCard.tsx';
import { SupportConfirmSheet } from './components/SupportConfirmSheet.tsx';
import { useBackendSupport } from './hook/useBackendSupport.ts';
import { clampPage, menuColumns, menuPageSize, pageCount, pageItems, reviewPageSize } from './utils/paging.ts';

const sampleMode = import.meta.env.DEV && import.meta.env.VITE_ORDER_SAMPLE === 'true';
// 단계별 안내: 안내 영역에 늘 서 있는 줄입니다. 다른 안내가 나오면 비켜 줍니다.
const guideLines: Record<'menu' | 'review' | 'complete', string[]> = {
  menu: ['① 메뉴를 골라 옵션과 수량을 정해 주세요.', '② 담은 뒤 화면 아래에서 주문을 확인해 주세요.'],
  review: ['① 담은 메뉴와 수량을 확인해 주세요.', '② 화면 아래에서 주문을 완료해 주세요.'],
  complete: ['주문번호를 확인한 뒤 새 주문을 시작해 주세요.'],
};

// 큰 글씨와 낮은 화면의 메뉴에서는 장바구니가 [담은 메뉴 보기] 뒤에 있습니다.
const cartInBarFor = (screen: string, settings: Settings) => screen === 'menu' && (settings.largeText || settings.lowScreen);

export function OrderPage() {
  const [controller] = useState(() => new OrderController(sampleMode ? createSampleOrderApi() : backendApi, fields => {
    if (import.meta.env.DEV) console.warn('주문 응답 검증 실패 필드:', fields);
  }));
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot);
  const [voiceController] = useState(() => new VoiceController({
    api: createVoiceApi(), recognitionOnly: sampleMode,
    // tool_calls are only an explanation. The backend marks a completed Cart write with this action.
    onResult: result => { if (result.actions.includes('cart_updated')) void controller.refreshCartAfterVoice(); },
  }));
  const voice = useSyncExternalStore(voiceController.subscribe, voiceController.getSnapshot);
  const [manualSettings, setManualSettings] = useState(() => {
    try { return readSettings(localStorage.getItem(settingsStorageKey) ?? localStorage.getItem('kiosk-sample-order-v1')); }
    catch { return { ...initialSettings }; }
  });
  const [automaticSettings, setAutomaticSettings] = useState<{ sessionId: string; values: Partial<Settings> }>({ sessionId: '', values: {} });
  const sessionId = state.session?.session_id ?? null;
  // 고객 설정만 저장합니다. 서버 제안으로 켠 설정은 새 세션·새로고침에서 끝납니다.
  const settings = useMemo(() => ({ ...manualSettings, ...(automaticSettings.sessionId === sessionId ? automaticSettings.values : {}) }), [manualSettings, automaticSettings, sessionId]);
  const [screen, setScreen] = useState<'menu' | 'review' | 'complete'>('menu');
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [menuPaging, setMenuPaging] = useState({ key: '', page: 0 });
  const [selected, setSelected] = useState<Product | null>(null);
  const [temperature, setTemperature] = useState<Temperature>('iced');
  const [quantity, setQuantity] = useState(1);
  const [supportOpen, setSupportOpen] = useState(false);
  const [storageWarning, setStorageWarning] = useState(false);
  const [orderNumber, setOrderNumber] = useState('');
  const [restartOpen, setRestartOpen] = useState(false);
  const [cartSheetOpen, setCartSheetOpen] = useState(false);
  const [autoOffClosed, setAutoOffClosed] = useState(false);
  // 버튼 강조 힌트: 고리와 그 한 줄 안내는 그 조작을 쓰거나 화면이 바뀔 때까지 남습니다(안내는 누름을 받지 않음).
  const [hint, setHint] = useState<HintKind | null>(null);
  const [reviewPage, setReviewPage] = useState(0);
  // 뺀 줄: 뺀 자리(최근 줄부터의 순서)와 그때의 화면·시트. 다음 터치나 화면·시트가 바뀌면 사라집니다.
  const [removed, setRemoved] = useState<{ item: CartItem; index: number; where: string } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const restartDialog = useRef<HTMLDialogElement>(null);
  const cartDialog = useRef<HTMLDialogElement>(null);
  const helpDialog = useRef<HTMLDialogElement>(null);
  const cartOpener = useRef<HTMLButtonElement>(null);
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
  useEffect(() => { if (voice.enabled) setAutoOffClosed(false); }, [voice.enabled]);
  // 키오스크가 켜는 크게 보기는 화면 설정 밖의 상태라 저장하지 않고, 새로고침·새 이용에서 끝납니다.
  const support = useSupportOffer({ settings, screen, sessionId: state.session?.session_id ?? null, orderDone: state.order !== null });
  // 크게 보기: 고객이 큰 글씨(200 %)를 켜면 그쪽이 앞섭니다.
  const largeView = support.largeView && !settings.largeText;
  useEffect(() => { try { localStorage.setItem(settingsStorageKey, JSON.stringify(manualSettings)); } catch { setStorageWarning(true); } }, [manualSettings]);
  useEffect(() => { heading.current?.focus(); }, [screen]);
  useLayoutEffect(() => { if (selected) dialog.current?.showModal(); else if (dialog.current?.open) dialog.current.close(); }, [selected]);
  useLayoutEffect(() => {
    if (restartOpen) restartDialog.current?.showModal();
    else if (restartDialog.current?.open) restartDialog.current.close();
  }, [restartOpen]);
  useLayoutEffect(() => {
    if (supportOpen) helpDialog.current?.showModal();
    else if (helpDialog.current?.open) helpDialog.current.close();
  }, [supportOpen]);
  useLayoutEffect(() => {
    if (cartSheetOpen) cartDialog.current?.showModal();
    else if (cartDialog.current?.open) cartDialog.current.close();
  }, [cartSheetOpen]);
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
      // 시트는 [화면 도움] 줄 바로 위에서 끝납니다. 주문 바가 안에서 스크롤되면 보이는 부분만 셉니다.
      const entries = bar.querySelector('.entry-row')?.getBoundingClientRect(), barBox = bar.getBoundingClientRect();
      root.style.setProperty('--entry-row-space', `${entries ? Math.max(0, Math.min(innerHeight, barBox.bottom) - Math.max(entries.top, barBox.top)) : 0}px`);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(bar);
    const main = root.querySelector('main'); if (main) observer.observe(main);
    // 짧은 창에서 주문 바가 안에서 스크롤되면 [화면 도움] 줄의 보이는 부분이 바뀌므로 다시 잽니다(화면 도움 시트가 그 위에 섬).
    window.addEventListener('resize', measure); bar.addEventListener('scroll', measure); measure();
    return () => { observer.disconnect(); window.removeEventListener('resize', measure); bar.removeEventListener('scroll', measure); document.documentElement.style.removeProperty('--order-actions-measured-height'); };
  }, [touchLog.root]);
  useEffect(() => {
    if (state.message) feedbackRef.current?.scrollIntoView({ block: 'start', behavior: 'instant' });
  }, [state.message, selected]);
  useEffect(() => {
    if (state.order) { setOrderNumber(state.order.order_number); setScreen('complete'); }
  }, [state.order]);

  const busy = state.status === 'loading' || state.status === 'saving';
  const writeDisabled = state.status !== 'ready' || state.order !== null;
  const backendSupport = useBackendSupport({
    sessionId, settings, read: touchLog.read,
    contextKey: JSON.stringify([sessionId, screen, category, menuPaging, state.cart?.version, settings]),
    enabled: !sampleMode && !writeDisabled && !selected && !supportOpen && !restartOpen && !cartSheetOpen
      && !voice.enabled && state.message === '' && !support.offer,
    onApply: key => { if (sessionId) setAutomaticSettings(current => ({ sessionId, values: { ...(current.sessionId === sessionId ? current.values : {}), [key]: true } })); },
  });
  const count = state.cart?.total_quantity ?? 0;
  const sum = state.cart?.total_amount ?? 0;
  const remaining = MAX_QUANTITY - (state.cart?.items.find(item => item.product_id === selected?.product_id && item.temperature === temperature)?.quantity ?? 0);
  const combinedEnlargement = settings.largeText && settings.largeButton;
  // 분류나 쪽 크기가 바뀌면 첫 쪽부터 보여 줍니다.
  const menuProducts = state.products.filter(product => category === 'all' || product.category === category);
  const menuSize = menuPageSize({ ...settings, largeView, voiceOn: screen === 'menu' && voice.enabled });
  const menuKey = `${category}:${menuSize}`;
  const menuPage = menuPaging.key === menuKey ? clampPage(menuPaging.page, menuProducts.length, menuSize) : 0;
  const menuPages = pageCount(menuProducts.length, menuSize);
  function toggleCombinedEnlargement() {
    const enabled = !(settings.largeText && settings.largeButton);
    setManualSettings(current => ({ ...current, largeText: enabled, largeButton: enabled }));
    clearAutomaticSettings(['largeText', 'largeButton']);
  }
  function clearAutomaticSettings(keys: (keyof Settings)[]) {
    setAutomaticSettings(current => {
      const values = { ...current.values };
      for (const key of keys) delete values[key];
      return { ...current, values };
    });
  }
  function closeOptions() { setSelected(null); opener.current?.focus(); }
  function closeRestart() { setRestartOpen(false); restartTrigger.current?.focus(); }
  function closeCartSheet() { setCartSheetOpen(false); cartOpener.current?.focus(); }
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
    setScreen('menu'); setOrderNumber(''); setCategory('all'); setMenuPaging({ key: '', page: 0 });
    if (resetCurrent && state.status === 'ready' && !state.order) await controller.restartCurrentOrder();
    else await controller.startNewOrder();
  }
  function openReview() {
    voiceController.setEnabled(false);
    setCartSheetOpen(false);
    setReviewPage(0);
    setScreen('review');
  }
  async function restartAfterUncertain() {
    if (!controller.abandonPending()) return;
    setScreen('menu'); setOrderNumber(''); setCategory('all');
    await startNewOrder();
  }
  const feedback = !busy && !state.message ? null : <>{busy && <p className="order-progress" role="status">{state.status === 'loading' ? orderCopy.preparing : orderCopy.saving}</p>}
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

  // 담은 줄은 최근 줄부터 보여 줍니다. 뺀 줄은 같은 화면·시트에서 다음 터치까지 제자리에 남습니다.
  const where = `${screen}:${cartSheetOpen}`;
  const cartLines: CartDisplayLine[] = [...(state.cart?.items ?? [])].reverse().map(item => ({ item, removed: false }));
  if (removed && removed.where === where && !cartLines.some(line => line.item.product_id === removed.item.product_id && line.item.temperature === removed.item.temperature)) {
    cartLines.splice(Math.min(removed.index, cartLines.length), 0, { item: removed.item, removed: true });
  }
  useNextTouch(removed !== null, touchLog.root, () => setRemoved(null), '.cart-lines');
  // 주문 확인은 화면 설정과 줄 수에 맞춰 쪽을 나눕니다(뺀 줄도 한 줄로 셉니다).
  const reviewSize = reviewPageSize(settings, cartLines.length);
  const reviewPages = pageCount(cartLines.length, reviewSize);
  const reviewPageNow = clampPage(reviewPage, cartLines.length, reviewSize);
  const lineActions: CartLineActions = {
    disabled: writeDisabled,
    onQuantity: (item, next) => void controller.updateQuantity(item.item_id, next),
    onRemove: item => {
      const index = cartLines.filter(line => !line.removed).findIndex(line => line.item.item_id === item.item_id);
      void controller.removeItem(item.item_id).then(done => { if (done) setRemoved({ item, index, where }); });
    },
    // 되돌리기는 같은 상품·온도·수량을 다시 담습니다(새 요청 키와 최신 버전). 서버는 줄을 끝에 두므로 맨 위로 올라옵니다.
    onUndo: () => {
      if (!removed) return;
      const { item } = removed;
      void controller.addItem({ product_id: item.product_id, temperature: item.temperature, quantity: item.quantity }).then(done => { if (done) setRemoved(null); });
    },
  };

  // 고객이 한 일의 알림(담았어요·수량을 바꿨어요·뺐어요·적용)은 잠깐 떴다가 briefNoticeMs가 지나거나 다음 터치에 닫힙니다.
  // 말로 주문이 오래 말이 없어 꺼지면 그 사실도 알림으로 보입니다.
  const autoOffShown = !voice.enabled && voice.autoOff !== null && !autoOffClosed;
  const appliedNotice = support.applied ? supportCopy[support.applied].applied : '';
  const hintLine = hint && !(hint === 'option-add' && selected) ? hintCopy[hint] : '';
  const notice = screen === 'complete' ? '' : appliedNotice || hintLine || state.notice || (autoOffShown ? voiceAutoOffNotice : '');
  const noticeIcon = appliedNotice ? 'check_circle' : hintLine ? 'pan_tool_alt' : null;
  useNextTouch((appliedNotice !== '' || state.notice !== '' || autoOffShown) && !feedback, touchLog.root, () => {
    controller.clearNotice(); setAutoOffClosed(true); support.closeApplied();
  });
  // 고리를 둘 조작: 담기 힌트는 옵션 시트의 [담기], 빼기 힌트는 가장 최근 줄의 [삭제](장바구니가 버튼 뒤에 있으면 [담은 메뉴 보기])
  const newestLine = cartLines.find(line => !line.removed)?.item;
  const ringTarget = !hint ? null : hint === 'option-add' ? 'cart-add'
    : cartInBarFor(screen, settings) && !cartSheetOpen ? 'cart-sheet-open' : newestLine ? `cart:${newestLine.product_id}:${temperatureLabel(newestLine.temperature)}:remove` : null;
  useLayoutEffect(() => {
    // 열린 창(dialog)이 있으면 그 안의 버튼을 먼저 찾습니다. 장바구니 창이 열려 있을 때 뒤에 가려진 같은 이름의 버튼에 고리를 두지 않으려고요.
    const selector = `[data-log-target="${ringTarget}"]`;
    const root = touchLog.root.current;
    const element = ringTarget ? root?.querySelector(`dialog[open] ${selector}`) ?? root?.querySelector(selector) : null;
    element?.classList.add('hint-ring');
    return () => element?.classList.remove('hint-ring');
  });
  useEffect(() => {
    if (!ringTarget) return;
    const used = (event: MouseEvent) => { if (event.target instanceof Element && event.target.closest(`[data-log-target="${ringTarget}"]`)) setHint(null); };
    document.addEventListener('click', used, true);
    return () => document.removeEventListener('click', used, true);
  }, [ringTarget]);
  useEffect(() => { setHint(null); }, [screen]);
  useSupportDraft({ receive: support.receive, hint: kind => setHint(kind), clear: () => { support.decline(); support.closeApplied(); setHint(null); } },
    { sessionId: state.session?.session_id ?? null, screen });
  // 큰 글씨에는 안내 영역이 없습니다(목록이 그 높이를 씁니다): 늘 서 있는 줄은 단계 표시 아래, 메뉴의 한 줄 안내는 상품 줄 위,
  // 버튼이 있는 오류 안내는 목록 자리 맨 위에 섭니다.
  const sheetOpen = selected !== null || cartSheetOpen;
  // 말로 주문이 켜진 메뉴: 주문 안내는 말로 주문 영역 안에 보이고, 장바구니는 한 줄만 보입니다.
  const voiceOn = screen === 'menu' && voice.enabled;
  // 늘 서 있는 줄: 단계별 안내를 켰을 때의 그 화면 안내입니다.
  const standing = settings.stepGuide ? guideLines[screen] : null;
  // 잠깐 뜨는 알림의 시간: 힌트 한 줄과 말로 주문이 꺼진 알림은 다음 터치(힌트는 그 조작)까지 남습니다.
  const briefShown = !feedback && !hintLine && (appliedNotice !== '' || state.notice !== '');
  useEffect(() => {
    if (!briefShown) return;
    const timer = setTimeout(() => { controller.clearNotice(); support.closeApplied(); }, briefNoticeMs);
    return () => clearTimeout(timer);
  }, [briefShown, appliedNotice, state.notice]);
  const standingTop = standing !== null && settings.largeText;
  // 키오스크의 제안은 시트가 열려 있거나 오류·처리 중 안내가 있는 동안 기다리고, 그 밖의 다음 터치에 닫힙니다.
  const offerCard = support.offer && !sheetOpen && !supportOpen && !restartOpen && !feedback ? <OfferCard support={support.offer.support} onAccept={support.accept} onDecline={support.decline} /> : null;
  useNextTouch(offerCard !== null, touchLog.root, support.decline, '.offer-card');
  const messagePlace = <MessagePlace feedback={sheetOpen ? null : feedback} offer={offerCard} notice={notice} kiosk={noticeIcon} standing={standingTop ? null : standing} />;
  const pageProducts = pageItems(menuProducts, menuPage, menuSize);
  // 메뉴 화면에는 비워 두는 안내 영역이 없습니다. 안내와 버튼이 있는 카드는 상품 목록 위에 뜨는 자리(쪽 넘김 줄 18 px 위)에 섭니다.
  const popup = <MessagePlace variant="popup" feedback={sheetOpen ? null : feedback} offer={offerCard} notice={notice} kiosk={noticeIcon} standing={null} />;
  // 단계별 안내(기본 글자 크기): 담은 메뉴 바로 위 한 줄 자리. 큰 글씨에서는 단계 표시 아래, 말로 주문 중에는 보이지 않습니다.
  const guideRow = screen === 'menu' && !standingTop && !voiceOn && standing;
  // 큰 글씨와 낮은 화면의 메뉴에서는 장바구니가 [담은 메뉴 보기] 뒤에 있습니다. 낮은 화면에서는 그 버튼이 금액을 담습니다.
  const cartInBar = cartInBarFor(screen, settings);
  const lowMenu = screen === 'menu' && settings.lowScreen;

  return <><div ref={touchLog.root} data-order-mode={sampleMode ? 'sample' : 'api'} data-listening={voiceOn && voice.phase === 'listening' ? 'on' : undefined} className={`kiosk ${settings.largeText ? 'large-text' : ''} ${settings.largeButton ? 'large-button' : ''} ${settings.simpleScreen ? 'simple-screen' : ''} ${settings.lowScreen ? 'low-screen' : ''} ${settings.highContrast ? 'high-contrast' : ''}${largeView ? ' large-view' : ''}${voiceOn ? ' voice-on' : ''}`}>
    {settings.lowScreen && <div className="low-screen-banner">
      {/* 낮은 화면의 비어 있는 위쪽 전체가 하나의 누름 자리입니다(화면 위로 올리기). 터치 기록에 남도록 주문 화면 안에 둡니다. */}
      <button type="button" className="raise-area" data-log-target="screen-position-pad" onClick={() => setManualSettings(current => ({ ...current, lowScreen: false }))}>
        <Icon name="arrow_upward" />화면 위로 올리기</button>
      <div className="banner-copy" aria-hidden="true"><p className="store-name">온기 카페</p><StepsBar screen={screen} /></div>
    </div>}
    <StoreRow />
    <main data-log-target="order-content">
      <StepsBar screen={screen} headingRef={heading} />
      {standingTop && standing && <div className="guide guide-lines" role="status">{standing.map(line => <p key={line}>{line}</p>)}</div>}
      {storageWarning && <p role="alert">화면 설정을 기억하지 못했어요. 새로고침하면 기본 화면으로 돌아갈 수 있어요.</p>}
      {screen === 'complete' ? <><div className="done-area"><DoneBlock orderNumber={orderNumber} items={state.order?.items ?? []} total={state.order?.total_amount ?? 0} /></div>{messagePlace}</>
        : screen === 'review' ? <div className="order-layout">{messagePlace}
          <ReviewBlock lines={cartLines} count={count} products={state.products} page={reviewPageNow} pages={reviewPages} size={reviewSize}
            actions={lineActions} onBack={() => setScreen('menu')} onPage={setReviewPage} /></div>
        : <div className="order-layout"><section className="menu-section" aria-label="상품 목록">
          <div className="tabs-row"><CategoryTabs category={category} onChange={setCategory} />
            <VoiceButton controller={voiceController} ready={(state.status === 'ready' || state.status === 'saving') && state.session !== null && state.order === null} sampleMode={sampleMode} /></div>
          <ProductGrid products={pageProducts} page={menuPage} pages={menuPages} rows={Math.ceil(menuSize / menuColumns(settings))} disabled={writeDisabled} asRows={settings.simpleScreen}
            popup={popup}
            onSelect={(product, button) => { opener.current = button; setSelected(product); setTemperature(product.temperatures[0] ?? null); setQuantity(1); }}
            onPage={page => setMenuPaging({ key: menuKey, page })} />
        </section>
          {guideRow && <div className="guide guide-row" role="status">{guideRow.map(line => <p key={line}>{line}</p>)}</div>}
          {!cartInBar && <CartPanel lines={cartLines} count={count} visible={1} actions={lineActions} openerRef={cartOpener} onOpenAll={() => setCartSheetOpen(true)} />}
          {voiceOn && <VoicePanel controller={voiceController} sampleMode={sampleMode} />}</div>}
    </main>
    <section ref={actionsRef} className="order-actions" aria-label="주문 진행">
      <ActionBar total={screen === 'complete' || lowMenu ? null : sum}
        cartButton={cartInBar ? { ref: cartOpener, amount: lowMenu ? sum : null, onClick: () => setCartSheetOpen(true) } : null}
        restart={screen === 'complete' ? null : { ref: restartTrigger, disabled: busy || state.status === 'uncertain', onClick: () => { voiceController.setEnabled(false); setRestartOpen(true); } }}
        primary={{ target: screen === 'complete' ? 'new-order' : screen === 'menu' ? 'review-open' : 'simulate-payment',
          label: screen === 'complete' ? '새 주문 시작' : screen === 'menu' ? '주문 확인' : '모의 주문 완료',
          disabled: screen === 'complete' ? busy : !count || writeDisabled,
          onClick: () => { if (screen === 'complete') { support.endUse(); void startNewOrder(); } else if (screen === 'menu') openReview(); else void controller.checkout(); } }} />
      <EntryRow supportOpen={supportOpen} onToggleSupport={() => setSupportOpen(!supportOpen)} onUndo={support.largeView ? support.undo : null} />
    </section>
    <HelpSheet ref={helpDialog} settings={settings} combined={combinedEnlargement}
      onToggle={key => { setManualSettings(current => ({ ...current, [key]: !settings[key] })); clearAutomaticSettings([key]); }}
      onCombined={toggleCombinedEnlargement}
      onReset={() => { support.resetView(); setAutomaticSettings({ sessionId: '', values: {} }); setManualSettings({ ...initialSettings }); }} onClose={() => setSupportOpen(false)}
      readAloud={<ReadAloudControls root={touchLog.root} voiceController={voiceController} screenKey={`${state.session?.session_id}:${screen}:${selected?.product_id ?? ''}:${restartOpen}:${cartSheetOpen}`} />} />
    <OptionSheet ref={dialog} product={selected} temperature={temperature} quantity={quantity} remaining={remaining} writeDisabled={writeDisabled}
      status={feedback} hint={hint === 'option-add' ? hintCopy['option-add'] : null}
      onTemperature={option => { setTemperature(option); setQuantity(1); }} onQuantity={setQuantity}
      onAdd={() => void addSelected()} onClose={closeOptions} />
    <CartSheet ref={cartDialog} open={cartSheetOpen} lines={cartLines} count={count} total={sum} actions={lineActions}
      status={feedback ?? (notice ? <p className="sheet-status" role="status">{notice}</p> : null)}
      reviewDisabled={!count || writeDisabled} onClose={closeCartSheet} onReview={openReview} />
    {backendSupport.preset && <SupportConfirmSheet key={backendSupport.preset} preset={backendSupport.preset} onAccept={backendSupport.accept} onDecline={backendSupport.decline} />}
    <dialog ref={restartDialog} className="options-dialog" aria-labelledby="restart-title" onCancel={event => { event.preventDefault(); closeRestart(); }}>
      <h2 id="restart-title">처음부터 주문할까요?</h2>
      <p>담은 메뉴를 비우고 새 주문을 시작합니다. 화면 도움 설정은 유지합니다.</p>
      <div className="order-feedback-actions"><button data-log-target="order-restart-cancel" onClick={closeRestart}>계속 주문하기</button>
        <button data-log-target="order-restart-confirm" disabled={busy || state.status === 'uncertain'} onClick={() => { setRestartOpen(false); void startNewOrder(true); }}>처음부터 주문하기</button></div>
    </dialog>
  </div><TouchLogPanel /></>;
}
