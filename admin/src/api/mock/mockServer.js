// 목 모드 전용: 관리자 API 9개와 로그인을 브라우저 안에서 흉내 낸다.
// 응답 모양과 규칙은 Swagger와 설계 문서(docs/admin-chat-api-design.md)를 따른다.
// 바꾼 내용(읽음, 상태, 메모)은 새로고침하면 처음으로 돌아간다.
import { ApiError } from '../client';
import { createMockData } from './mockData';

const MOCK_USERNAME = 'admin';
const MOCK_PASSWORD = 'sleeby';
const MOCK_TOKEN = 'mock-admin-token';
const TOKEN_TTL_MS = 12 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
// 비용 계산용 가정 단가 (입력·출력 100만 토큰당 달러)
const PRICE_INPUT = 0.1;
const PRICE_OUTPUT = 0.5;

const db = createMockData();
const turnById = new Map(db.turns.map((turn) => [turn.turn_id, turn]));

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const now = () => new Date().toISOString();

function fail(status, code, message) {
  throw new ApiError(status, code, message);
}

function inRange(iso, params) {
  if (params.from && iso < params.from) return false;
  if (params.to && iso >= params.to) return false;
  return true;
}

function paginate(items, params) {
  const page = Math.max(1, Number(params.page ?? 1));
  const size = Math.min(100, Math.max(1, Number(params.size ?? 20)));
  return {
    items: items.slice((page - 1) * size, page * size),
    page,
    size,
    total_count: items.length,
  };
}

function kstDayStart(daysAgo) {
  const kst = new Date(Date.now() + KST_OFFSET_MS);
  const midnight = Date.UTC(kst.getUTCFullYear(), kst.getUTCMonth(), kst.getUTCDate());
  return new Date(midnight - KST_OFFSET_MS - daysAgo * DAY_MS).toISOString();
}

// ---- 문의 ----
function conversationOf(inquiry) {
  if (!inquiry.chat_id || !inquiry.context_last_turn_id) return [];
  const boundary = turnById.get(inquiry.context_last_turn_id).finished_at;
  return db.turns
    .filter((t) => t.chat_id === inquiry.chat_id && t.finished_at <= boundary)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .map((t) => ({
      turn_id: t.turn_id,
      question: t.question,
      parent_turn_id: t.parent_turn_id,
      status: t.status,
      mode: t.mode,
      answer: t.answer,
      cited_sources: t.cited_sources,
      // 문의 상세에는 검색 후보 상위 3개만 준다
      retrieved_sources: t.retrieved_sources.slice(0, 3),
      is_trigger: t.turn_id === inquiry.trigger_turn_id,
      created_at: t.created_at,
    }));
}

function inquirySummary(inquiry) {
  return {
    id: inquiry.id,
    reference_no: inquiry.reference_no,
    name: inquiry.name,
    content_preview: inquiry.content.slice(0, 80),
    origin: inquiry.origin,
    status: inquiry.status,
    is_unread: inquiry.first_viewed_at === null,
    has_conversation: conversationOf(inquiry).length > 0,
    created_at: inquiry.created_at,
  };
}

function inquiryDetail(inquiry) {
  return {
    ...inquirySummary(inquiry),
    email: inquiry.email,
    content: inquiry.content,
    internal_note: inquiry.internal_note,
    first_viewed_at: inquiry.first_viewed_at,
    completed_at: inquiry.completed_at,
    updated_at: inquiry.updated_at,
    chat_id: inquiry.chat_id,
    trigger_turn_id: inquiry.trigger_turn_id,
    conversation: conversationOf(inquiry),
  };
}

function filterInquiries(params, { ignoreStatus = false } = {}) {
  const status = params.status ?? 'unresolved';
  return db.inquiries.filter((inquiry) => {
    if (!inRange(inquiry.created_at, params)) return false;
    if (params.origin && inquiry.origin !== params.origin) return false;
    if (params.viewed === 'true' && inquiry.first_viewed_at === null) return false;
    if (params.viewed === 'false' && inquiry.first_viewed_at !== null) return false;
    if (ignoreStatus || status === 'all') return true;
    if (status === 'unresolved') return inquiry.status !== 'completed';
    return inquiry.status === status;
  });
}

function inquiryCounts(params) {
  const items = filterInquiries(params, { ignoreStatus: true });
  const count = (predicate) => items.filter(predicate).length;
  return {
    received: count((i) => i.status === 'received'),
    in_progress: count((i) => i.status === 'in_progress'),
    completed: count((i) => i.status === 'completed'),
    unresolved: count((i) => i.status !== 'completed'),
    unread: count((i) => i.first_viewed_at === null),
    total: items.length,
  };
}

function patchInquiry(inquiry, body) {
  const keys = Object.keys(body ?? {});
  if (!keys.length) fail(422, 'validation_error', '바꿀 내용을 하나 이상 보내 주세요.');
  if (body.internal_note != null && body.internal_note.length > 2000) {
    fail(422, 'validation_error', '메모는 2,000자까지 쓸 수 있어요.');
  }
  const time = now();
  if (body.viewed === true && inquiry.first_viewed_at === null) inquiry.first_viewed_at = time;
  if (body.status) {
    inquiry.status = body.status;
    inquiry.completed_at = body.status === 'completed' ? (inquiry.completed_at ?? time) : null;
  }
  if (body.internal_note != null) inquiry.internal_note = body.internal_note;
  inquiry.updated_at = time;
  return inquiryDetail(inquiry);
}

// ---- 질문 로그 ----
function turnSummary(turn) {
  return {
    turn_id: turn.turn_id,
    chat_id: turn.chat_id,
    question: turn.question,
    status: turn.status,
    mode: turn.mode,
    latency_ms: turn.latency_ms,
    rating: turn.feedback?.rating ?? null,
    created_at: turn.created_at,
  };
}

function costOf(turn) {
  if (turn.prompt_tokens == null || turn.completion_tokens == null) return null;
  return (turn.prompt_tokens * PRICE_INPUT + turn.completion_tokens * PRICE_OUTPUT) / 1_000_000;
}

function turnDetail(turn) {
  return {
    ...turnSummary(turn),
    parent_turn_id: turn.parent_turn_id,
    answer: turn.answer,
    show_contact: turn.show_contact,
    retrieved_sources: turn.retrieved_sources,
    cited_sources: turn.cited_sources,
    reason: turn.reason,
    error_code: turn.error_code,
    prompt_tokens: turn.prompt_tokens,
    completion_tokens: turn.completion_tokens,
    estimated_cost_usd: costOf(turn),
    llm_model: turn.llm_model,
    config_name: turn.config_name,
    feedback: turn.feedback,
    inquiries: db.inquiries
      .filter((i) => i.trigger_turn_id === turn.turn_id)
      .map((i) => ({ id: i.id, reference_no: i.reference_no })),
  };
}

function listTurns(params) {
  const turns = db.turns.filter((turn) => {
    if (!inRange(turn.created_at, params)) return false;
    if (params.mode && turn.mode !== params.mode) return false;
    if (params.status && turn.status !== params.status) return false;
    if (params.chat_id && turn.chat_id !== params.chat_id) return false;
    const rating = turn.feedback?.rating ?? 'none';
    return !params.rating || rating === params.rating;
  });
  // 한 대화를 이어 볼 때는 오래된 순, 그 밖에는 최신순
  turns.sort((a, b) =>
    params.chat_id
      ? a.created_at.localeCompare(b.created_at)
      : b.created_at.localeCompare(a.created_at),
  );
  return paginate(turns.map(turnSummary), params);
}

// ---- 답 못 한 질문 ----
function unansweredTurns(params) {
  const range = params.from || params.to ? params : { from: kstDayStart(29) };
  return db.turns.filter(
    (t) =>
      t.status === 'completed' &&
      inRange(t.created_at, range) &&
      (t.mode === 'unknown' || t.mode === 'partial' || t.feedback?.rating === 'down'),
  );
}

// 검색 1순위 FAQ가 같은 질문끼리 묶는다 (설계의 초기안)
function groupKey(turn) {
  return turn.retrieved_sources[0]?.source_id ?? 'none';
}

function buildGroups(params) {
  const groups = new Map();
  unansweredTurns(params).forEach((turn) => {
    const key = groupKey(turn);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(turn);
  });
  return [...groups.entries()]
    .map(([key, turns]) => {
      const latest = turns.reduce((a, b) => (a.created_at > b.created_at ? a : b));
      const ids = new Set(turns.map((t) => t.turn_id));
      return {
        group_key: key,
        source_title: key === 'none' ? null : latest.retrieved_sources[0].title,
        representative_question: latest.question,
        occurrence_count: turns.length,
        unknown_count: turns.filter((t) => t.mode === 'unknown').length,
        partial_count: turns.filter((t) => t.mode === 'partial').length,
        downvote_count: turns.filter((t) => t.feedback?.rating === 'down').length,
        last_seen_at: latest.created_at,
        inquiries: db.inquiries
          .filter((i) => ids.has(i.trigger_turn_id))
          .map((i) => ({ id: i.id, reference_no: i.reference_no })),
        turns,
      };
    })
    .sort((a, b) => b.occurrence_count - a.occurrence_count);
}

// 묶음 계산에만 쓰는 turns는 응답에서 뺀다
function withoutTurns(group) {
  const copy = { ...group };
  delete copy.turns;
  return copy;
}

function groupDetail(key, params) {
  const group = buildGroups(params).find((g) => g.group_key === key);
  if (!group) fail(404, 'not_found', '묶음을 찾을 수 없어요.');
  const counts = new Map();
  group.turns.forEach((t) => counts.set(t.question, (counts.get(t.question) ?? 0) + 1));
  return {
    group: withoutTurns(group),
    variants: [...counts.entries()]
      .map(([question, count]) => ({ question, count }))
      .sort((a, b) => b.count - a.count),
    turns: paginate(
      group.turns.sort((a, b) => b.created_at.localeCompare(a.created_at)).map(turnSummary),
      params,
    ),
  };
}

// ---- 대시보드 ----
function dashboard(params) {
  const range = params.from || params.to ? params : { from: kstDayStart(6), to: kstDayStart(-1) };
  const turns = db.turns.filter((t) => inRange(t.created_at, range));
  const completed = turns.filter((t) => t.status === 'completed');
  const failed = turns.filter((t) => t.status === 'failed');
  const modeCounts = { answer: 0, partial: 0, unknown: 0, offtopic: 0, greeting: 0 };
  completed.forEach((t) => (modeCounts[t.mode] += 1));
  const failedByReason = {};
  failed.forEach((t) => (failedByReason[t.error_code] = (failedByReason[t.error_code] ?? 0) + 1));
  const ratio = (num, den) => (den ? num / den : null);
  const average = (values) =>
    values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : null;
  const feedback = turns.filter((t) => t.feedback);
  const costs = turns.map(costOf).filter((c) => c != null);

  // 한국 날짜별 질문 수. 빈 날짜는 0
  const daily = [];
  const start = new Date(range.from).getTime();
  const end = new Date(range.to ?? kstDayStart(-1)).getTime();
  for (let day = start; day < end; day += DAY_MS) {
    const from = new Date(day).toISOString();
    const to = new Date(day + DAY_MS).toISOString();
    daily.push({
      date: new Date(day + KST_OFFSET_MS).toISOString().slice(0, 10),
      count: turns.filter((t) => t.created_at >= from && t.created_at < to).length,
    });
  }

  const sourceCounts = new Map();
  completed.forEach((t) =>
    new Set(t.cited_sources.map((s) => s.source_id)).forEach((id) => {
      const title = t.cited_sources.find((s) => s.source_id === id).title;
      const entry = sourceCounts.get(id) ?? { source_id: id, title, count: 0 };
      entry.count += 1;
      sourceCounts.set(id, entry);
    }),
  );

  return {
    question_count: turns.length,
    mode_counts: modeCounts,
    failed_count: failed.length,
    failed_by_reason: failedByReason,
    average_latency_ms: average(completed.map((t) => t.latency_ms)),
    uncertain_ratio: ratio(
      modeCounts.partial + modeCounts.unknown,
      modeCounts.answer + modeCounts.partial + modeCounts.unknown,
    ),
    feedback_count: feedback.length,
    positive_feedback_ratio: ratio(
      feedback.filter((t) => t.feedback.rating === 'up').length,
      feedback.length,
    ),
    estimated_cost_usd: costs.length ? costs.reduce((sum, c) => sum + c, 0) : null,
    average_cost_usd: average(costs),
    unresolved_inquiry_count: db.inquiries.filter((i) => i.status !== 'completed').length,
    unread_inquiry_count: db.inquiries.filter((i) => i.first_viewed_at === null).length,
    daily_questions: daily,
    top_sources: [...sourceCounts.values()].sort((a, b) => b.count - a.count).slice(0, 5),
  };
}

// ---- 라우터 ----
export async function handle(method, url, body, token) {
  await wait(150);
  const [path, search = ''] = url.split('?');
  const params = Object.fromEntries(new URLSearchParams(search));

  if (method === 'POST' && path === '/api/admin/tokens') {
    if (body?.username !== MOCK_USERNAME || body?.password !== MOCK_PASSWORD) {
      fail(401, 'unauthorized', '아이디 또는 비밀번호가 올바르지 않아요.');
    }
    return {
      token: MOCK_TOKEN,
      display_name: '관리자',
      expires_at: new Date(Date.now() + TOKEN_TTL_MS).toISOString(),
    };
  }
  if (token !== MOCK_TOKEN) fail(401, 'unauthorized', '다시 로그인해 주세요.');

  const segments = path.replace('/api/admin/', '').split('/');
  const [resource, id] = segments;

  if (resource === 'tokens' && id === 'current') {
    return {
      display_name: '관리자',
      expires_at: new Date(Date.now() + TOKEN_TTL_MS).toISOString(),
    };
  }
  if (resource === 'inquiries' && !id) {
    const items = filterInquiries(params).map(inquirySummary);
    return paginate(items, params);
  }
  if (resource === 'inquiry-counts') return inquiryCounts(params);
  if (resource === 'inquiries') {
    const inquiry = db.inquiries.find((i) => i.id === id);
    if (!inquiry) fail(404, 'not_found', '문의를 찾을 수 없어요.');
    return method === 'PATCH' ? patchInquiry(inquiry, body) : inquiryDetail(inquiry);
  }
  if (resource === 'turns' && !id) return listTurns(params);
  if (resource === 'turns') {
    const turn = turnById.get(id);
    if (!turn) fail(404, 'not_found', '질문을 찾을 수 없어요.');
    return turnDetail(turn);
  }
  if (resource === 'unanswered-groups' && !id) {
    return paginate(buildGroups(params).map(withoutTurns), params);
  }
  if (resource === 'unanswered-groups') return groupDetail(decodeURIComponent(id), params);
  if (resource === 'dashboard') return dashboard(params);
  return fail(404, 'not_found', '찾을 수 없어요.');
}
