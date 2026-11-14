import { useEffect, useRef, useState } from 'react';

// 조회 하나를 불러온다. key(조회 조건을 문자열로 만든 값)가 바뀌거나 reload를 부르면 다시 부른다.
// 늦게 온 이전 응답은 버리고, 새 응답이 올 때까지 이전 데이터를 그대로 보여 준다
export function useAsync(load, key = '') {
  const [result, setResult] = useState({ key: null, version: -1, data: null, error: null });
  const [version, setVersion] = useState(0);
  const loadRef = useRef(load);

  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let isActive = true;
    loadRef.current().then(
      (data) => isActive && setResult({ key, version, data, error: null }),
      (error) => isActive && setResult((prev) => ({ ...prev, key, version, error })),
    );
    return () => {
      isActive = false;
    };
  }, [key, version]);

  const isLoading = result.key !== key || result.version !== version;
  return {
    data: result.data,
    error: isLoading ? null : result.error,
    isLoading,
    reload: () => setVersion((value) => value + 1),
    setData: (data) => setResult((prev) => ({ ...prev, data })),
  };
}
