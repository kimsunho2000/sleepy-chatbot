import { useEffect, useState } from 'react';
import FeedbackBar from './FeedbackBar';
import Icon from './Icon';
import InquiryForm from './InquiryForm';

const MODE_LABEL = {
  partial: '일부만 확인된 답변이에요',
  unknown: '자료에서 확인되지 않았어요',
  offtopic: '답변 범위 밖의 질문이에요',
  error: '답변하지 못했어요',
};

// retryAt(서버가 정한 다시 시도 가능 시각)까지 남은 초. 지나면 0
function useSecondsUntil(retryAt) {
  const left = () => (retryAt ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1000)) : 0);
  const [seconds, setSeconds] = useState(left);
  useEffect(() => {
    if (!retryAt) return undefined;
    const timer = setInterval(() => {
      const next = Math.max(0, Math.ceil((retryAt - Date.now()) / 1000));
      setSeconds(next);
      if (next === 0) clearInterval(timer);
    }, 1000);
    return () => clearInterval(timer);
  }, [retryAt]);
  return seconds;
}

// 답변 근거(출처)는 고객 화면에 보여 주지 않는다. 관리자 화면에서만 확인한다
export default function MessageBubble({ message, chat, isLatest }) {
  const [isFormOpen, setIsFormOpen] = useState(Boolean(message.isFormOpen));
  const waitSeconds = useSecondsUntil(message.retryAt);

  if (message.role === 'user') {
    return <div className="msg user">{message.text}</div>;
  }

  // 답변 뒤 문의 카드는 show_contact=true일 때, 그 밖의 문의 버튼은 안내 메시지에 붙은 경로로 연다
  const origin = message.showContact ? 'uncertain_answer_card' : message.inquiryOrigin;
  // 답변이 배지와 같은 문구로 시작하면 배지를 숨겨 같은 말이 두 번 보이지 않게 한다
  const modeLabel = MODE_LABEL[message.mode];
  const label = modeLabel && !message.text.trim().startsWith(modeLabel) ? modeLabel : null;
  // 다시 시도는 마지막 메시지에서만 보여 준다. 뒤에 다른 대화가 이어졌으면 의미가 없다
  const canRetry = Boolean(message.retryQuestion) && isLatest;
  // 서버에 저장된 답변(turn)만 평가할 수 있다. 인사는 평가할 내용이 없어 뺀다
  const canRate = Boolean(message.turnId) && message.mode !== 'greeting';

  return (
    <div className={`msg bot mode-${message.mode}`}>
      <span className="av" aria-hidden="true">
        <Icon name="moon" />
      </span>
      <div className="bot-text">
        {label && <span className="mode-label">{label}</span>}
        <p>{message.text}</p>
        {canRate && <FeedbackBar message={message} chat={chat} />}
        {canRetry && waitSeconds > 0 && (
          <p className="wait-note">{waitSeconds}초 후에 다시 시도할 수 있어요.</p>
        )}
        {!isFormOpen && (origin || canRetry) && (
          <div className="chips">
            {canRetry && (
              <button
                type="button"
                className="pill"
                disabled={chat.isLoading || waitSeconds > 0}
                onClick={() => chat.retry(message.retryQuestion)}
              >
                다시 시도
              </button>
            )}
            {origin && (
              <button type="button" className="pill solid" onClick={() => setIsFormOpen(true)}>
                담당자에게 문의 남기기
              </button>
            )}
          </div>
        )}
        {isFormOpen && origin && (
          <InquiryForm
            origin={origin}
            cardChatId={message.chatId ?? null}
            triggerTurnId={message.turnId}
            chat={chat}
            onClose={() => setIsFormOpen(false)}
          />
        )}
      </div>
    </div>
  );
}
