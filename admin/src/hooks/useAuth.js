import { useCallback, useEffect, useState } from 'react';
import { api, setToken, setUnauthorizedHandler } from '../api/client';

// 토큰은 탭 안(sessionStorage)에만 둔다. 탭을 닫으면 로그아웃된다
const STORAGE_KEY = 'sleeby-admin-token';

function readStored() {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function store(value) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, value);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // 저장소를 못 쓰면 이 탭이 열려 있는 동안만 로그인이 유지된다
  }
}

export function useAuth() {
  // checking: 저장된 토큰이 아직 유효한지 확인 중
  const [state, setState] = useState(() => ({
    status: readStored() ? 'checking' : 'signed-out',
    admin: null,
    notice: '',
  }));

  const signOut = useCallback((notice = '') => {
    setToken(null);
    store(null);
    setState({ status: 'signed-out', admin: null, notice });
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => signOut('로그인이 만료됐어요. 다시 로그인해 주세요.'));
  }, [signOut]);

  useEffect(() => {
    const saved = readStored();
    if (!saved) return;
    setToken(saved);
    api
      .currentToken()
      .then((admin) => setState({ status: 'signed-in', admin, notice: '' }))
      .catch((error) => {
        // 401은 등록한 핸들러가 만료 안내와 함께 이미 로그아웃했다. 덮어쓰지 않는다
        if (error.status === 401) return;
        // 일시 장애일 수 있으니 저장된 토큰은 지우지 않는다. 새로고침하면 다시 확인한다
        setToken(null);
        setState({
          status: 'signed-out',
          admin: null,
          notice:
            '서버와 연결하지 못해 로그인 상태를 확인하지 못했어요. 잠시 후 새로고침해 주세요.',
        });
      });
  }, [signOut]);

  const signIn = useCallback(async (username, password) => {
    const result = await api.login(username, password);
    setToken(result.token);
    store(result.token);
    setState({
      status: 'signed-in',
      admin: { display_name: result.display_name, expires_at: result.expires_at },
      notice: '',
    });
  }, []);

  return { ...state, signIn, signOut };
}
