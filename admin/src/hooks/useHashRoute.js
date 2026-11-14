import { useCallback, useEffect, useState } from 'react';

// 주소 예: #/inquiries?id=… , #/logs?chat_id=…
// 해시 주소를 쓰면 정적 배포(Vercel)에서 새로고침해도 서버 리라이트 설정이 필요 없다
export const ROUTES = ['inquiries', 'unanswered', 'logs', 'dashboard'];

function parse() {
  const [path, search = ''] = window.location.hash.replace(/^#\/?/, '').split('?');
  return {
    page: ROUTES.includes(path) ? path : 'inquiries',
    params: Object.fromEntries(new URLSearchParams(search)),
  };
}

export function useHashRoute() {
  const [route, setRoute] = useState(parse);

  useEffect(() => {
    const onChange = () => setRoute(parse());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  const navigate = useCallback((page, params = {}) => {
    const search = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value != null && value !== ''),
    ).toString();
    window.location.hash = `/${page}${search ? `?${search}` : ''}`;
  }, []);

  return { ...route, navigate };
}
