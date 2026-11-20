import './topCluster.css';

/** [이전] "n / m" [다음]. 쪽 번호는 0부터 받고 1부터 보여 줍니다. 쪽이 바뀌면 화면 읽기 프로그램이 새 쪽 번호를 읽습니다(aria-live). */
export function Pager({ page, pages, target, onChange }: { page: number; pages: number; target: string; onChange: (page: number) => void }) {
  return <div className="pager">
    <button type="button" data-log-target={`${target}:prev`} disabled={page <= 0} onClick={() => onChange(page - 1)}>이전</button>
    <span className="page" aria-live="polite">{page + 1} / {pages}</span>
    <button type="button" data-log-target={`${target}:next`} disabled={page >= pages - 1} onClick={() => onChange(page + 1)}>다음</button>
  </div>;
}
