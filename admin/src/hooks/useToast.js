import { useCallback, useEffect, useRef, useState } from 'react';

const TOAST_MS = 2400;

export function useToast() {
  const [message, setMessage] = useState('');
  const timerRef = useRef(0);

  const show = useCallback((text) => {
    setMessage(text);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setMessage(''), TOAST_MS);
  }, []);

  useEffect(() => () => clearTimeout(timerRef.current), []);

  return { message, show };
}
