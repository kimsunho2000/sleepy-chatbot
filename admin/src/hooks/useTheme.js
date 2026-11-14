import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'sleeby-admin-theme';
const media = () => window.matchMedia('(prefers-color-scheme: dark)');

function readSaved() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved === 'light' || saved === 'dark' ? saved : null;
  } catch {
    return null;
  }
}

// 처음에는 시스템 설정을 따르고, 사용자가 고르면 그 값을 기억한다
export function useTheme() {
  const [saved, setSaved] = useState(readSaved);
  const [systemDark, setSystemDark] = useState(() => media().matches);

  useEffect(() => {
    const query = media();
    const onChange = (event) => setSystemDark(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    if (saved) document.documentElement.dataset.theme = saved;
    else delete document.documentElement.dataset.theme;
  }, [saved]);

  const isDark = saved ? saved === 'dark' : systemDark;

  const toggle = useCallback(() => {
    const next = isDark ? 'light' : 'dark';
    setSaved(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // 저장하지 못해도 이 화면에서는 바뀐다
    }
  }, [isDark]);

  return { isDark, toggle };
}
