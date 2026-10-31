import { useEffect, useState } from 'react';

const dateFormat = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: 'long', day: 'numeric', weekday: 'short' });
const timeFormat = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: true });

export function KioskClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return <div className="kiosk-clock" aria-label="현재 날짜와 시각">
    <span>{dateFormat.format(now)}</span><time dateTime={now.toISOString()}>{timeFormat.format(now)}</time>
  </div>;
}
