import { useCallback, useRef, useState } from 'react';
import { ApiError, createChat, deleteFeedback, putFeedback, sendTurn } from '../api/client';

// 오류 코드별 고객 안내 (Swagger error.code)
const ERROR_TEXT = {
  validation_error: '입력값을 확인해 주세요.',
  rate_limited: '질문을 너무 빨리 보내셨어요. 잠시 후 다시 질문해 주세요.',
  daily_limit_reached: '오늘 이용 가능한 질문 수를 넘었어요. 담당자에게 문의를 남겨 주세요.',
  service_busy: '지금은 답변이 어려워요. 담당자에게 문의를 남겨 주세요.',
  ai_unavailable: '일시적으로 답변이 어려워요. 다시 시도하시거나 담당자에게 문의를 남겨 주세요.',
  ai_timeout: '답변이 늦어지고 있어요. 다시 시도하시거나 담당자에게 문의를 남겨 주세요.',
  db_unavailable: '일시적인 오류예요. 잠시 후 다시 시도해 주세요.',
  unauthorized: '대화가 만료됐어요. 질문을 다시 보내 주시면 새 대화로 이어 갈게요.',
  not_found: '대화가 만료됐어요. 질문을 다시 보내 주시면 새 대화로 이어 갈게요.',
};
const DEFAULT_ERROR = '서버와 연결하지 못했어요. 잠시 후 다시 시도해 주세요.';
// 문의 폼으로 이어 줄 오류와, "다시 시도" 버튼을 보여 줄 오류
const INQUIRY_CODES = new Set([
  'daily_limit_reached',
  'service_busy',
  'ai_unavailable',
  'ai_timeout',
]);
const RETRY_CODES = new Set([
  'rate_limited',
  'ai_unavailable',
  'ai_timeout',
  'db_unavailable',
  'network_error',
]);
// 대화 토큰이 더는 통하지 않는 경우: 다음 질문은 새 대화로 보낸다
const EXPIRED_CODES = new Set(['unauthorized', 'not_found']);

const newId = () => crypto.randomUUID();

export function useChat() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  // 대화 정보는 화면에 그리지 않으므로 ref로 둔다. 새로고침하면 사라져 새 대화가 된다
  const chatRef = useRef(null); // { id, token }
  const chatPromiseRef = useRef(null); // 만드는 중인 대화. 동시에 두 번 만들지 않게 같이 기다린다
  const lastCompletedTurnIdRef = useRef(null);
  const hasSavedTurnRef = useRef(false); // 완료·실패 turn이 서버에 하나라도 저장됐는지
  const isLoadingRef = useRef(false);
  // 초기화할 때마다 1씩 올린다. 초기화 전에 보낸 요청의 응답은 번호가 달라 버린다
  const epochRef = useRef(0);

  const append = useCallback((...items) => setMessages((prev) => [...prev, ...items]), []);

  const forgetChat = useCallback(() => {
    chatRef.current = null;
    chatPromiseRef.current = null;
    lastCompletedTurnIdRef.current = null;
    hasSavedTurnRef.current = false;
  }, []);

  const ensureChat = useCallback(() => {
    if (chatRef.current) return Promise.resolve(chatRef.current);
    if (!chatPromiseRef.current) {
      const promise = createChat()
        .then((created) => {
          const chat = { id: created.chat_id, token: created.chat_token };
          // 만드는 사이에 초기화됐으면 이 대화는 기억하지 않는다
          if (chatPromiseRef.current === promise) chatRef.current = chat;
          return chat;
        })
        .finally(() => {
          if (chatPromiseRef.current === promise) chatPromiseRef.current = null;
        });
      chatPromiseRef.current = promise;
    }
    return chatPromiseRef.current;
  }, []);

  // 대화 토큰이 만료됐을 때. 그사이 다른 대화로 바뀌었으면 건드리지 않는다
  const expireChat = useCallback(
    (chatId) => {
      if (chatRef.current?.id === chatId) forgetChat();
    },
    [forgetChat],
  );

  const ask = useCallback(
    async (text, { echo = true } = {}) => {
      const question = text.trim();
      // 응답을 기다리는 동안에는 새 질문을 받지 않는다 (재전송하면 LLM 비용이 두 번 든다)
      if (!question || isLoadingRef.current) return;
      const epoch = epochRef.current;
      const isCurrent = () => epochRef.current === epoch;
      if (echo) append({ id: newId(), role: 'user', text: question });
      isLoadingRef.current = true;
      setIsLoading(true);
      let chat = null;
      try {
        chat = await ensureChat();
        if (!isCurrent()) return;
        const turn = await sendTurn({
          chatId: chat.id,
          token: chat.token,
          question,
          parentTurnId: lastCompletedTurnIdRef.current,
        });
        if (!isCurrent()) return;
        lastCompletedTurnIdRef.current = turn.turn_id;
        hasSavedTurnRef.current = true;
        append({
          id: turn.turn_id,
          role: 'bot',
          chatId: chat.id,
          turnId: turn.turn_id,
          mode: turn.mode,
          text: turn.answer,
          showContact: turn.show_contact,
          feedback: turn.feedback,
        });
      } catch (error) {
        if (!isCurrent()) return;
        const code = error instanceof ApiError ? error.code : 'network_error';
        if (error instanceof ApiError && error.turnId) hasSavedTurnRef.current = true;
        if (EXPIRED_CODES.has(code) && chat) expireChat(chat.id);
        const retryAfter = error instanceof ApiError ? error.retryAfter : null;
        append({
          id: newId(),
          role: 'bot',
          mode: 'error',
          text: ERROR_TEXT[code] ?? DEFAULT_ERROR,
          inquiryOrigin: INQUIRY_CODES.has(code) ? 'direct_form' : null,
          retryQuestion: RETRY_CODES.has(code) ? question : null,
          // 서버가 기다리라고 한 시각까지 "다시 시도"를 잠근다
          retryAt: retryAfter ? Date.now() + retryAfter * 1000 : null,
        });
      } finally {
        if (isCurrent()) {
          isLoadingRef.current = false;
          setIsLoading(false);
        }
      }
    },
    [append, ensureChat, expireChat],
  );

  // 실패 후 다시 시도: 질문 말풍선을 다시 쌓지 않는다. 부모는 마지막 완료 turn 그대로다
  const retry = useCallback((question) => ask(question, { echo: false }), [ask]);

  // 답변 평가. next가 null이면 취소한다. 실패하면 화면 상태를 바꾸지 않고 오류를 던진다
  const sendFeedback = useCallback(
    async (message, next) => {
      const chat = chatRef.current;
      // 초기화·만료로 대화 토큰이 없으면 서버도 받지 않으므로 보내지 않는다
      if (!chat || chat.id !== message.chatId) {
        throw new ApiError(404, 'not_found', '이전 대화의 답변이라 평가를 남길 수 없어요.');
      }
      const target = { chatId: chat.id, token: chat.token, turnId: message.turnId };
      let saved;
      try {
        saved = next ? await putFeedback({ ...target, ...next }) : await deleteFeedback(target);
      } catch (error) {
        // 서버는 토큰이 맞지 않아도 404(not_found)를 준다. 화면의 turn은 모두 이 대화에서 받은 것이라
        // turn을 못 찾는 404는 사실상 없으므로, 두 코드 모두 대화 만료로 본다
        if (error instanceof ApiError && EXPIRED_CODES.has(error.code)) expireChat(chat.id);
        throw error;
      }
      const feedback = saved ? { rating: saved.rating, reason: saved.reason ?? null } : null;
      setMessages((prev) =>
        prev.map((item) => (item.id === message.id ? { ...item, feedback } : item)),
      );
    },
    [expireChat],
  );

  // 상담사 연결: 실시간 상담이 아니라 담당자 문의로 이어 준다
  const requestAgent = useCallback(() => {
    append(
      { id: newId(), role: 'user', text: '상담사 연결' },
      {
        id: newId(),
        role: 'bot',
        mode: 'notice',
        text: '상담사 실시간 연결은 지원하지 않아요. 문의를 남겨 주시면 담당자가 확인 후 이메일로 연락드릴게요.',
        inquiryOrigin: 'agent_request',
      },
    );
  }, [append]);

  // 하단 "담당자 문의": 바로 문의 폼을 연다
  const requestInquiry = useCallback(() => {
    append({
      id: newId(),
      role: 'bot',
      mode: 'notice',
      text: '문의 내용을 남겨 주시면 담당자가 확인 후 이메일로 연락드릴게요.',
      inquiryOrigin: 'direct_form',
      isFormOpen: true,
    });
  }, [append]);

  // 초기화: 화면을 비우고 다음 질문부터 새 대화를 만든다. 서버의 이전 기록은 지우지 않는다.
  // 답변을 기다리는 중이어도 바로 초기화하고, 늦게 온 응답은 epoch가 달라 버린다
  const reset = useCallback(() => {
    epochRef.current += 1;
    forgetChat();
    isLoadingRef.current = false;
    setIsLoading(false);
    setMessages([]);
  }, [forgetChat]);

  // 문의에 붙일 대화 정보
  const getInquiryContext = useCallback(
    () => ({
      chat: chatRef.current,
      lastCompletedTurnId: lastCompletedTurnIdRef.current,
      hasSavedTurn: hasSavedTurnRef.current,
    }),
    [],
  );

  return {
    messages,
    isLoading,
    ask,
    retry,
    reset,
    requestAgent,
    requestInquiry,
    sendFeedback,
    ensureChat,
    expireChat,
    getInquiryContext,
  };
}
