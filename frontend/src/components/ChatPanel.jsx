import { useEffect, useRef, useState } from 'react';
import { useChat } from '../hooks/useChat';
import { useChatResize } from '../hooks/useChatResize';
import Icon from './Icon';
import MessageBubble from './MessageBubble';

const GREETING = '안녕하세요! 무엇을 도와드릴까요?';
const RESIZE_HINT = '끌어서 크기 조절 (두 번 누르면 처음 크기)';

const TOPICS = [
  {
    name: '제품 소개',
    hint: '무엇인지, 어떤 원리인지',
    questions: [
      '구성품에는 어떤 것들이 들어 있나요?',
      '슬리비는 어떤 원리로 수면과 이완을 돕도록 설계되었나요?',
    ],
  },
  {
    name: '사용 방법·유의사항',
    hint: '착용, 충전, 주의할 점',
    questions: [
      '슬리비를 사용하려면 스마트폰이나 전용 앱이 필요한가요?',
      '여행할 때 비행기나 기차 안에서 사용해도 되나요?',
      '슬리비가 충전되지 않을 때는 어떻게 하나요?',
    ],
  },
  {
    name: '구매·문의',
    hint: '배송, 교환, 환불, 상담',
    questions: [
      '제품을 주문하면 배송까지 얼마나 걸리나요?',
      '제품이 귀에 맞지 않으면 교환하거나 환불받을 수 있나요?',
      '상담원 또는 1:1 문의는 어디에서 신청할 수 있나요?',
    ],
  },
];

export default function ChatPanel({ isSolo = false, onClose }) {
  const { messages, isLoading, sessionId, ask, stop, reset } = useChat();
  const [input, setInput] = useState('');
  const [topic, setTopic] = useState(null);
  const [isConfirmingReset, setIsConfirmingReset] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const bottomRef = useRef(null);
  const chatRef = useRef(null);
  // 전체 화면(#/chat)에서는 창이 화면을 채우므로 크기 조절을 쓰지 않는다
  const resize = useChatResize(chatRef, !isSolo);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // 전체 창으로 확대한 상태에서는 Esc로 원래 크기로 돌아간다
  useEffect(() => {
    if (!isExpanded && !isConfirmingReset) return undefined;
    const onKeyDown = (event) => {
      if (event.key !== 'Escape') return;
      // 확인 창이 떠 있으면 그것만 닫는다
      if (isConfirmingReset) setIsConfirmingReset(false);
      else setIsExpanded(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isExpanded, isConfirmingReset]);

  const submit = (event) => {
    event.preventDefault();
    ask(input);
    setInput('');
  };

  const confirmReset = () => {
    reset();
    setTopic(null);
    setIsConfirmingReset(false);
  };

  const isTalking = messages.length > 0;
  const expandLabel = isExpanded ? '원래 크기로 줄이기' : '전체 창으로 확대';
  const closeLabel = isSolo ? '나가기' : '닫기';
  const canResize = !isSolo && !isExpanded;

  return (
    <section
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
          <b>SLEEBY</b>
          <span>안내 도우미</span>
        </div>
        <div className="tools">
          {isTalking && (
            <button
              type="button"
              className="tool is-icon"
              aria-label="새로고침 (대화 초기화)"
              title="새로고침 (대화 초기화)"
              onClick={() => setIsConfirmingReset(true)}
            >
              <Icon name="refresh" />
            </button>
          )}
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
            <Icon name="minus" />
          </button>
        </div>
      </header>

      <div className="chat-body">
        <div className="msgs">
          <div className="msg bot">
            <span className="av" aria-hidden="true">
              ☾
            </span>
            <div className="bot-text">
              <p>{GREETING}</p>
            </div>
          </div>
          {!isTalking && (
            <div className="welcome">
              <p>제품 자료와 FAQ를 근거로 답해요. 수면 효과나 의학적 판단은 안내하지 않아요.</p>
              <div className="topics">
                {TOPICS.map((item) => (
                  <button
                    key={item.name}
                    type="button"
                    className={`topic ${topic?.name === item.name ? 'is-on' : ''}`}
                    onClick={() => setTopic(item)}
                  >
                    <span>
                      <small>{item.hint}</small>
                      <strong>{item.name}</strong>
                    </span>
                    <span aria-hidden="true">→</span>
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
                      onClick={() => ask(question)}
                    >
                      {question}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {messages.map((message, index) => (
            <MessageBubble key={index} message={message} sessionId={sessionId} />
          ))}
          {isLoading && (
            <div className="msg bot">
              <span className="av" aria-hidden="true">
                ☾
              </span>
              <span className="typing" aria-label="답변을 찾는 중">
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
            aria-label="질문 입력"
            placeholder="궁금한 점을 입력해 주세요"
            value={input}
            onChange={(event) => setInput(event.target.value)}
          />
          {isLoading ? (
            <button type="button" className="send" aria-label="답변 멈추기" onClick={stop}>
              ■
            </button>
          ) : (
            <button type="submit" className="send" aria-label="보내기" disabled={!input.trim()}>
              ↑
            </button>
          )}
        </form>
        <p className="chat-note">AI 답변은 자료에 없는 내용을 확인하지 못할 수 있어요.</p>
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
