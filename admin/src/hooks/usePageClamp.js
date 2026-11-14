import { useEffect } from 'react';

// 상태 변경 등으로 지금 페이지가 마지막 페이지보다 뒤로 밀리면 마지막 페이지로 당긴다.
// 그대로 두면 빈 목록만 보이고 페이지 이동 버튼도 사라져 빠져나올 수 없다
export function usePageClamp({ page, size, total, isLoading, setPage }) {
  useEffect(() => {
    if (isLoading || total == null) return;
    const pages = Math.max(1, Math.ceil(total / size));
    if (page > pages) setPage(pages);
  }, [page, size, total, isLoading, setPage]);
}
