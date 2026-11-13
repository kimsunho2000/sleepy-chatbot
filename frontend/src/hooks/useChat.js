import { useCallback, useRef, useState } from 'react';
import { resetChat, sendChat } from '../api/client';

export function useChat() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const sessionIdRef = useRef(null);
  const abortRef = useRef(null);

  const ask = useCallback(async (text) => {
    const question = text.trim();
    if (!question) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setMessages((prev) => [...prev, { role: 'user', text: question }]);
    setIsLoading(true);
    try {
      const data = await sendChat(question, sessionIdRef.current, controller.signal);
      sessionIdRef.current = data.session_id;
      setMessages((prev) => [...prev, { role: 'bot', ...data, text: data.answer }]);
    } catch (error) {
      if (error.name === 'AbortError') return;
      setMessages((prev) => [
        ...prev,
        {
          role: 'bot',
          mode: 'error',
          text: '서버와 연결하지 못했어요. 잠시 후 다시 시도해 주세요.',
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const reset = useCallback(async () => {
    const sessionId = sessionIdRef.current;
    sessionIdRef.current = null;
    setMessages([]);
    if (sessionId) {
      try {
        await resetChat(sessionId);
      } catch {
        // 화면은 이미 비웠으므로 서버 초기화 실패는 무시한다
      }
    }
  }, []);

  return { messages, isLoading, sessionId: sessionIdRef, ask, stop, reset };
}
