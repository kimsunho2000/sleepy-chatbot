// 화면 표시 규칙: 서버는 UTC로 주고받고, 화면은 한국 시간으로 보여 준다
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

const dateTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Seoul',
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
});

// 11/13 14:09 처럼 짧게 보여 준다 (한국 시간)
export function formatDateTime(iso) {
  if (!iso) return '—';
  const part = Object.fromEntries(
    dateTime.formatToParts(new Date(iso)).map(({ type, value }) => [type, value]),
  );
  return `${part.month}/${part.day} ${part.hour}:${part.minute}`;
}

export function formatAgo(iso, now = Date.now()) {
  const minutes = Math.round((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return '방금';
  if (minutes < 60) return `${minutes}분 전`;
  if (minutes < 1440) return `${Math.round(minutes / 60)}시간 전`;
  return `${Math.round(minutes / 1440)}일 전`;
}

// 한국 날짜 0시를 UTC ISO로. 기간 필터는 from 포함, to 미포함이다
function kstMidnight(daysFromToday, now = Date.now()) {
  const kst = new Date(now + KST_OFFSET_MS);
  const midnight = Date.UTC(kst.getUTCFullYear(), kst.getUTCMonth(), kst.getUTCDate());
  return new Date(midnight - KST_OFFSET_MS + daysFromToday * DAY_MS).toISOString();
}

// days: 오늘 포함 며칠. null이면 전체 기간
export function periodRange(days, now = Date.now()) {
  if (!days) return {};
  return { from: kstMidnight(1 - days, now), to: kstMidnight(1, now) };
}

export const PERIODS = [
  { value: '1', label: '오늘' },
  { value: '7', label: '최근 7일' },
  { value: '30', label: '최근 30일' },
  { value: 'all', label: '전체 기간' },
];

export const periodDays = (value) => (value === 'all' ? null : Number(value));

export function formatRatio(value) {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

export function formatSeconds(ms) {
  return ms == null ? '—' : `${(ms / 1000).toFixed(2)}초`;
}

export function formatUsd(value, digits = 4) {
  return value == null ? '—' : `$${value.toFixed(digits)}`;
}

// 검색 점수는 확률이 아니므로 백분율로 바꾸지 않는다
export function formatScore(score) {
  return score == null ? '—' : score.toFixed(3);
}

export const MODE_LABEL = {
  answer: '답변',
  partial: '부분 답변',
  unknown: '답변 불가',
  offtopic: '범위 밖',
  greeting: '인사',
};

export const STATUS_LABEL = { received: '접수', in_progress: '처리 중', completed: '완료' };

export const ORIGIN_LABEL = {
  uncertain_answer_card: '답변 뒤 문의 카드',
  agent_request: '상담사 연결',
  direct_form: '직접 문의 폼',
};

export const FEEDBACK_REASON_LABEL = {
  wrong: '틀림',
  insufficient: '부족함',
  irrelevant: '질문과 무관',
};

export const ERROR_CODE_LABEL = {
  llm_rate_limit: 'OpenAI 속도 제한',
  llm_quota: '크레딧 소진',
  llm_timeout: '시간 초과',
  llm_parse_error: '응답 해석 실패',
  llm_error: 'LLM 오류',
  retrieval_error: '검색 실패',
};
