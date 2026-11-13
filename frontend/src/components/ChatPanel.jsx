import { useEffect, useRef, useState } from 'react';
import { useChat } from '../hooks/useChat';
import { useChatResize } from '../hooks/useChatResize';
import Icon from './Icon';
import MessageBubble from './MessageBubble';

const RESIZE_HINT = '끌어서 크기 조절 (두 번 누르면 처음 크기)';
const MAX_QUESTION_LENGTH = 500;

// 자주 묻는 질문 버튼. 문구는 data/faq.json·product.json의 질문과 같게 둔다
const TOPICS = [
  {
    name: '제품 소개',
    hint: '슬리비가 어떤 제품인지',
    questions: [
      '슬리비는 어떤 제품인가요?',
      '슬리비는 어떤 원리로 수면과 이완을 돕도록 설계되었나요?',
      '구성품에는 어떤 것들이 들어 있나요?',
    ],
  },
  {
    name: '사용 방법 · 유의사항',
    hint: '사용법, 충전, 주의할 점',
    questions: [
      '슬리비를 사용하려면 스마트폰이나 전용 앱이 필요한가요?',
      '충전은 어떻게 하나요?',
      '여행할 때 비행기나 기차 안에서 사용해도 되나요?',
    ],
  },
  {
    name: '구매 · 문의',
    hint: '구매처, 배송, 교환, 문의 방법',
    questions: [
      '제품을 주문하면 배송까지 얼마나 걸리나요?',
      '제품이 귀에 맞지 않으면 교환하거나 환불받을 수 있나요?',
      '상담원 또는 1:1 문의는 어디에서 신청할 수 있나요?',
    ],
  },
];

export default function ChatPanel({
  id,
  isSolo = false,
  isOpen = true,
  pendingQuestion = null,
  onClose,
}) {
  const chat = useChat();
  const { messages, isLoading, ask, reset, requestAgent, requestInquiry } = chat;
  const handledQuestionRef = useRef(null);
  const inputRef = useRef(null);
  const [input, setInput] = useState('');
  const [topic, setTopic] = useState(null);
  const [isConfirmingReset, setIsConfirmingReset] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const bottomRef = useRef(null);
  const chatRef = useRef(null);
  // 전체 화면(#/chat)에서는 창이 화면을 채우므로 크기 조절을 쓰지 않는다
  const resize = useChatResize(chatRef, !isSolo);

  // 랜딩 페이지에서 고른 질문을 한 번만 보낸다. 답변을 기다리는 중이면 끝난 뒤에 보낸다
  useEffect(() => {
    if (!pendingQuestion || handledQuestionRef.current === pendingQuestion.id || isLoading) return;
    handledQuestionRef.current = pendingQuestion.id;
    ask(pendingQuestion.text);
  }, [pendingQuestion, isLoading, ask]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // 창이 열리면 바로 입력할 수 있게 입력창으로 포커스를 옮긴다
  useEffect(() => {
    if (isOpen) inputRef.current?.focus();
  }, [isOpen]);

  // Esc: 확인 창 → 확대 → 창 순서로 하나씩 닫는다. 전체 화면(#/chat)은 창을 닫지 않는다
  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key !== 'Escape') return;
      if (isConfirmingReset) setIsConfirmingReset(false);
      else if (isExpanded) setIsExpanded(false);
      else if (!isSolo) onClose?.();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, isExpanded, isConfirmingReset, isSolo, onClose]);

  const isTalking = messages.length > 0;

  const submit = (event) => {
    event.preventDefault();
    if (isLoading) return;
    ask(input);
    setInput('');
  };

  const confirmReset = () => {
    reset();
    setTopic(null);
    setInput('');
    setIsConfirmingReset(false);
  };

  // 대화가 없으면 확인 없이 처음 화면으로 돌아간다
  const startOver = () => (isTalking ? setIsConfirmingReset(true) : confirmReset());

  const expandLabel = isExpanded ? '작게 보기' : '크게 보기';
  const closeLabel = isSolo ? '홈페이지로 돌아가기' : '닫기';
  const canResize = !isSolo && !isExpanded;

  return (
    <section
      id={id}
      ref={chatRef}
      className={`chat ${isSolo ? 'is-solo' : ''} ${isExpanded ? 'is-expanded' : ''} ${
        resize.active ? 'is-resizing' : ''
      }`}
      aria-label="슬리비 안내 도우미"
    >
      {canResize && (
        <>
          <button
            type="button"
            className="chat-resize is-corner"
            data-active={resize.active === 'corner'}
            title={RESIZE_HINT}
            aria-label="채팅창 크기 조절. 방향키로 크기를 바꾸고 Enter로 처음 크기로 되돌려요"
            onKeyDown={resize.onKeyDown}
            {...resize.handleProps('corner')}
          />
          <span
            className="chat-resize is-left"
            data-active={resize.active === 'left'}
            title={RESIZE_HINT}
            aria-hidden="true"
            {...resize.handleProps('left')}
          />
          <span
            className="chat-resize is-top"
            data-active={resize.active === 'top'}
            title={RESIZE_HINT}
            aria-hidden="true"
            {...resize.handleProps('top')}
          />
        </>
      )}
      <header className="chat-head">
        <div className="chat-name">
          <b>SLEEPY</b>
          <span>슬리비 안내 도우미</span>
        </div>
        <div className="tools">
          <button
            type="button"
            className="tool is-icon"
            aria-label="상담사 연결"
            title="상담사 연결"
            onClick={requestAgent}
          >
            <Icon name="headset" />
          </button>
          <button
            type="button"
            className="tool is-icon"
            aria-label="처음부터 다시"
            title="처음부터 다시"
            onClick={startOver}
          >
            <Icon name="refresh" />
          </button>
          {!isSolo && (
            <button
              type="button"
              className="tool is-icon is-expand"
              aria-label={expandLabel}
              aria-pressed={isExpanded}
              title={expandLabel}
              onClick={() => setIsExpanded((value) => !value)}
            >
              <Icon name={isExpanded ? 'collapse' : 'expand'} />
            </button>
          )}
          <button
            type="button"
            className="tool is-icon"
            aria-label={closeLabel}
            title={closeLabel}
            onClick={onClose}
          >
            <Icon name={isSolo ? 'collapse' : 'close'} />
          </button>
        </div>
      </header>

      <div className="chat-body" aria-live="polite">
        {!isTalking && (
          <div className="welcome">
            <div className="welcome-head">
              <span className="moon" aria-hidden="true">
                <Icon name="moon" />
              </span>
              <h2>무엇이 궁금하세요?</h2>
              <p>
                원하는 분야를 먼저 골라 주세요.
                <br />
                자료에 없는 내용은 담당자 문의로 연결해 드릴게요.
              </p>
            </div>
            <div className="topics">
              {TOPICS.map((item) => (
                <button
                  key={item.name}
                  type="button"
                  className={`topic ${topic?.name === item.name ? 'is-on' : ''}`}
                  aria-pressed={topic?.name === item.name}
                  onClick={() => setTopic(item)}
                >
                  <span>
                    <small>{item.hint}</small>
                    <strong>{item.name}</strong>
                  </span>
                  <Icon name="chevron" />
                </button>
              ))}
            </div>
            {topic && (
              <div className="chips questions">
                {topic.questions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    className="pill"
                    disabled={isLoading}
                    onClick={() => ask(question)}
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="msgs">
          {messages.map((message, index) => (
            <MessageBubble
              key={message.id}
              message={message}
              chat={chat}
              isLatest={index === messages.length - 1}
            />
          ))}
          {isLoading && (
            <div className="msg bot">
              <span className="av" aria-hidden="true">
                <Icon name="moon" />
              </span>
              <span className="typing" aria-label="답변 작성 중">
                <i />
                <i />
                <i />
              </span>
            </div>
          )}
        </div>
        <div ref={bottomRef} />
      </div>

      <footer className="chat-foot">
        <form className={`composer ${input.trim() ? 'has-text' : ''}`} onSubmit={submit}>
          <input
            id="chat-input"
            ref={inputRef}
            aria-label="질문 입력"
            placeholder="슬리비에 대해 물어보세요"
            autoComplete="off"
            maxLength={MAX_QUESTION_LENGTH}
            value={input}
            onChange={(event) => setInput(event.target.value)}
          />
          {/* 서버는 답변 생성을 중간에 멈추지 않으므로 멈추기 버튼 없이, 기다리는 동안 전송만 막는다 */}
          <button
            type="submit"
            className="send"
            aria-label="보내기"
            disabled={isLoading || !input.trim()}
          >
            <Icon name="send" />
          </button>
        </form>
        <p className="chat-note">
          AI 답변은 부정확할 수 있어요 ·{' '}
          <button type="button" className="note-link" onClick={requestInquiry}>
            담당자 문의
          </button>{' '}
          ·{' '}
          <button type="button" className="note-link" onClick={requestAgent}>
            상담사 연결
          </button>
        </p>
      </footer>

      {isConfirmingReset && (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="alertdialog"
            aria-modal="true"
            aria-describedby="reset-message"
          >
            <p id="reset-message">이전 질문과 답변 기록은 돌아가지 못합니다.</p>
            <div className="modal-actions">
              <button
                type="button"
                className="pill"
                autoFocus
                onClick={() => setIsConfirmingReset(false)}
              >
                대화 이어가기
              </button>
              <button type="button" className="pill solid" onClick={confirmReset}>
                새 대화
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
