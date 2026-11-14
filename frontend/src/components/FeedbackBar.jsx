import { useId, useState } from 'react';
import Icon from './Icon';

// 👎 이유 (Swagger FeedbackRequest.reason). 고르지 않아도 👎는 저장된다
const REASONS = [
  { value: 'wrong', label: '틀렸어요' },
  { value: 'insufficient', label: '부족해요' },
  { value: 'irrelevant', label: '질문과 무관해요' },
];
const SAVE_ERROR = '평가를 저장하지 못했어요. 잠시 후 다시 눌러 주세요.';
// 대화 토큰이 더는 통하지 않으면 다시 눌러도 같으므로 버튼을 거두고 이 안내만 남긴다
const EXPIRED_TEXT = '이전 대화의 답변이라 평가를 남길 수 없어요.';
const EXPIRED_CODES = new Set(['unauthorized', 'not_found']);

// 답변 아래 👍/👎. 같은 버튼을 다시 누르면 평가를 취소한다
export default function FeedbackBar({ message, chat }) {
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [isLocked, setIsLocked] = useState(false);
  const questionId = useId();
  const rating = message.feedback?.rating ?? null;
  const reason = message.feedback?.reason ?? null;

  const save = async (next) => {
    // 저장 중에는 버튼을 막아 요청 순서가 뒤바뀌지 않게 한다
    if (isSaving) return;
    setIsSaving(true);
    setError(null);
    try {
      await chat.sendFeedback(message, next);
    } catch (failure) {
      // 서버 문구는 상황마다 달라 화면에는 고정 문구만 쓴다
      if (EXPIRED_CODES.has(failure.code)) {
        setIsLocked(true);
        setError(EXPIRED_TEXT);
      } else {
        setError(SAVE_ERROR);
      }
    } finally {
      setIsSaving(false);
    }
  };

  const toggle = (value) => save(rating === value ? null : { rating: value });

  if (isLocked) {
    // 바깥 여백은 그대로 두고, 버튼이 사라진 이유를 스크린리더에도 알린다
    return (
      <div className="feedback">
        <p className="feedback-error" role="alert">
          {error}
        </p>
      </div>
    );
  }

  return (
    <div className="feedback">
      <div className="feedback-row" role="group" aria-labelledby={questionId}>
        <span id={questionId} className="feedback-question">
          답변이 도움이 됐나요?
        </span>
        <button
          type="button"
          className={`feedback-btn${rating === 'up' ? ' is-on' : ''}`}
          aria-label="도움이 됐어요"
          aria-pressed={rating === 'up'}
          disabled={isSaving}
          onClick={() => toggle('up')}
        >
          <Icon name="thumbsUp" />
        </button>
        <button
          type="button"
          className={`feedback-btn${rating === 'down' ? ' is-on' : ''}`}
          aria-label="도움이 안 됐어요"
          aria-pressed={rating === 'down'}
          disabled={isSaving}
          onClick={() => toggle('down')}
        >
          <Icon name="thumbsDown" />
        </button>
      </div>
      {rating === 'down' && (
        <div className="chips feedback-reasons" role="group" aria-label="아쉬운 점">
          {REASONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`pill${reason === option.value ? ' is-on' : ''}`}
              aria-pressed={reason === option.value}
              disabled={isSaving}
              onClick={() =>
                // 고른 이유를 다시 누르면 이유만 지우고 👎는 남긴다
                save({ rating: 'down', reason: reason === option.value ? null : option.value })
              }
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
      {error && (
        <p className="feedback-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
