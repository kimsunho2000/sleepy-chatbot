// isLoading: 다음 페이지를 불러오는 동안 이전 수치로 연타하지 않게 막는다
export default function Pager({ page, size, total, isLoading = false, onChange }) {
  const pages = Math.max(1, Math.ceil(total / size));
  if (pages <= 1) return null;
  return (
    <nav className="pager" aria-label="페이지" aria-busy={isLoading}>
      <button
        type="button"
        className="btn small"
        disabled={isLoading || page <= 1}
        onClick={() => onChange(page - 1)}
      >
        이전
      </button>
      <span className="sub num">
        {page} / {pages}
      </span>
      <button
        type="button"
        className="btn small"
        disabled={isLoading || page >= pages}
        onClick={() => onChange(page + 1)}
      >
        다음
      </button>
    </nav>
  );
}
