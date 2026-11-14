// 불러오는 중·오류·빈 목록 표시. 데이터가 있으면 children을 그린다
export default function State({ isLoading, error, isEmpty, emptyText, onRetry, children }) {
  if (error) {
    return (
      <div className="state error" role="alert">
        {error.message || '불러오지 못했어요.'}{' '}
        {onRetry && (
          <button type="button" className="link" onClick={onRetry}>
            다시 시도
          </button>
        )}
      </div>
    );
  }
  if (isLoading && isEmpty) return <div className="state">불러오는 중…</div>;
  if (isEmpty) return <div className="empty">{emptyText}</div>;
  return children;
}
