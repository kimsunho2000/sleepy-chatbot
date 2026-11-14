import { ERROR_CODE_LABEL, MODE_LABEL, STATUS_LABEL } from '../lib/format';

const MODE_TONE = {
  answer: 'tone-ok',
  partial: 'tone-warn',
  unknown: 'tone-crit',
  offtopic: 'tone-info',
  greeting: 'tone-muted',
};
const STATUS_TONE = { received: 'tone-crit', in_progress: 'tone-warn', completed: 'tone-ok' };

// 실패(시스템 장애)와 답변 불가(근거 없음)를 다른 배지로 구별한다
export function ModeBadge({ status, mode, errorCode }) {
  if (status === 'failed') {
    return (
      <span className="badge tone-muted" title={ERROR_CODE_LABEL[errorCode] ?? errorCode}>
        실패{errorCode ? ` · ${ERROR_CODE_LABEL[errorCode] ?? errorCode}` : ''}
      </span>
    );
  }
  return <span className={`badge ${MODE_TONE[mode] ?? 'tone-muted'}`}>{MODE_LABEL[mode]}</span>;
}

export function StatusBadge({ status }) {
  return <span className={`badge ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>;
}

export function RatingMark({ rating }) {
  if (rating === 'up') return <span aria-label="좋아요">👍</span>;
  if (rating === 'down') return <span aria-label="싫어요">👎</span>;
  return <span className="sub">-</span>;
}
