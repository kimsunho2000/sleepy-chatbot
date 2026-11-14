// 목 모드 전용 가짜 데이터. 이름·이메일·문의·수치는 모두 예시다.
// 출처 제목은 실제 데이터(data/*.json)에서 가져와 화면이 실제와 같은 모양으로 보이게 한다.
import faq from '../../../../data/faq.json';
import product from '../../../../data/product.json';

const ITEMS = new Map([...faq, ...product].map((item) => [item.faq_id, item]));
const title = (id) => ITEMS.get(id)?.question ?? null;
const answerOf = (id) => ITEMS.get(id)?.answer ?? '';

const UNKNOWN_ANSWER =
  '죄송해요, 문의하신 내용은 아직 확인된 안내 자료가 없어 정확히 답변드리기 어려워요. 담당자에게 문의해 주시면 확인 후 안내드릴게요.';
const OFFTOPIC_ANSWER =
  '저는 슬리비 제품 안내를 돕는 챗봇이에요. 제품 특징, 사용 방법, 유의사항, 구매 방법을 물어봐 주세요.';
const GREETING_ANSWER =
  '안녕하세요, 슬리비 제품 안내를 돕는 챗봇이에요. 궁금한 점을 편하게 물어봐 주세요.';

// [질문, 판단, 근거 FAQ, 검색 후보 FAQ, 판단 사유]
const SCENARIOS = [
  [
    '충전은 어떻게 하나요?',
    'answer',
    ['P07'],
    ['P07', 'Q24', 'Q34', 'P08', 'Q28'],
    'P07에 충전 방법이 있음',
  ],
  [
    '완전히 충전하려면 얼마나 걸려요?',
    'answer',
    ['Q28'],
    ['Q28', 'P07', 'Q24', 'Q34', 'Q70'],
    'Q28이 직접 답함',
  ],
  ['배송 며칠 걸려요?', 'answer', ['Q70'], ['Q70', 'Q81', 'Q77', 'Q79', 'Q76'], 'Q70이 직접 답함'],
  [
    '해외로도 보내 주나요?',
    'answer',
    ['Q77'],
    ['Q77', 'Q70', 'Q79', 'Q81', 'Q76'],
    'Q77에 해외 배송 안내가 있음',
  ],
  ['앱 깔아야 해요?', 'answer', ['Q03'], ['Q03', 'Q12', 'Q22', 'P01', 'Q07'], 'Q03이 직접 답함'],
  [
    '옆으로 누워서 자도 돼요?',
    'answer',
    ['Q40'],
    ['Q40', 'Q52', 'Q22', 'Q85', 'Q03'],
    'Q40이 직접 답함',
  ],
  ['의료기기예요?', 'answer', ['Q58'], ['Q58', 'Q52', 'P01', 'Q03', 'Q40'], 'Q58이 직접 답함'],
  ['슬리비가 뭐예요?', 'answer', ['P01'], ['P01', 'Q58', 'Q03', 'Q22', 'Q12'], 'P01이 제품 소개'],
  [
    '한쪽만 잃어버렸는데 하나만 살 수 있어요?',
    'answer',
    ['Q73'],
    ['Q73', 'Q76', 'Q79', 'Q83', 'Q70'],
    'Q73에 개별 구매 안내가 있음',
  ],
  [
    '한쪽만 사면 가격이 얼마예요?',
    'unknown',
    [],
    ['Q73', 'Q76', 'Q79', 'Q81', 'Q70'],
    '가격 정보가 검색 결과에 없음',
  ],
  [
    '분실한 왼쪽 가격 알려주세요',
    'unknown',
    [],
    ['Q73', 'Q79', 'Q76', 'Q83', 'Q70'],
    '가격 정보 없음',
  ],
  [
    '중이염 치료 중인데 써도 돼요?',
    'partial',
    ['Q52'],
    ['Q52', 'Q58', 'Q40', 'Q03', 'P01'],
    '일반 안내만 있고 특정 질환 답은 없음',
  ],
  [
    '케이스 불이 계속 깜빡여요',
    'partial',
    ['Q31'],
    ['Q31', 'Q24', 'Q34', 'P08', 'P07'],
    '표시등 안내는 있으나 원인 판단 불가',
  ],
  [
    '알람 기능 나중에 생기나요?',
    'unknown',
    [],
    ['Q07', 'Q03', 'Q12', 'P01', 'Q22'],
    '기능 추가 계획 자료 없음',
  ],
  [
    '기내에서 충전 케이스 써도 되나요?',
    'unknown',
    [],
    ['Q34', 'P08', 'Q85', 'Q77', 'P07'],
    '기내 사용 자료 없음',
  ],
  [
    '30개 단체 구매 할인 돼요?',
    'partial',
    ['Q76'],
    ['Q76', 'Q73', 'Q79', 'Q83', 'Q70'],
    '대량 구매 문의 안내만 있음',
  ],
  [
    '상담사랑 얘기하고 싶어요',
    'answer',
    ['Q83'],
    ['Q83', 'Q79', 'Q76', 'Q73', 'Q81'],
    'Q83에 문의 방법이 있음',
  ],
  ['오늘 날씨 어때?', 'offtopic', [], ['P01', 'Q03', 'Q12', 'Q40', 'Q22'], '제품과 관련 없는 질문'],
  ['안녕하세요', 'greeting', [], ['P01', 'Q03', 'Q22', 'Q12', 'Q58'], '인사'],
];

// 실패 turn의 원인 (설계 문서의 error_code)
const FAILURES = ['llm_rate_limit', 'llm_timeout', 'retrieval_error', 'llm_quota'];

function seededRandom(seed) {
  let value = seed;
  return () => {
    value = (value * 1103515245 + 12345) % 2147483648;
    return value / 2147483648;
  };
}

function uuid(random) {
  const hex = () => Math.floor(random() * 16).toString(16);
  const part = (n) => Array.from({ length: n }, hex).join('');
  return `${part(8)}-${part(4)}-4${part(3)}-a${part(3)}-${part(12)}`;
}

function sources(ids, random, cited = false) {
  return ids.map((id, index) => ({
    rank: index + 1,
    source_id: id,
    title: title(id),
    score: Number((cited ? 0.62 - index * 0.04 : 0.6 - index * 0.06 - random() * 0.05).toFixed(4)),
  }));
}

function makeTurn(random, chatId, parentId, scenario, createdAt) {
  const [question, mode, citedIds, retrievedIds, reason] = scenario;
  const failed = random() < 0.05;
  const latency = Math.round(900 + random() * 4200);
  const finishedAt = new Date(new Date(createdAt).getTime() + latency).toISOString();
  const base = {
    turn_id: uuid(random),
    chat_id: chatId,
    parent_turn_id: parentId,
    question,
    created_at: createdAt,
    finished_at: finishedAt,
    llm_model: 'gpt-6-luna',
    config_name: 'default',
    feedback: null,
  };
  if (failed) {
    return {
      ...base,
      status: 'failed',
      mode: null,
      answer: null,
      show_contact: false,
      reason: null,
      error_code: FAILURES[Math.floor(random() * FAILURES.length)],
      latency_ms: null,
      prompt_tokens: null,
      completion_tokens: null,
      retrieved_sources: [],
      cited_sources: [],
    };
  }
  const supportNeeded = citedIds.some((id) => ITEMS.get(id)?.support_required);
  const answer =
    {
      unknown: UNKNOWN_ANSWER,
      offtopic: OFFTOPIC_ANSWER,
      greeting: GREETING_ANSWER,
    }[mode] ?? answerOf(citedIds[0]);
  const feedbackRoll = random();
  const feedback =
    feedbackRoll < 0.18
      ? { rating: 'up', reason: null, updated_at: finishedAt }
      : feedbackRoll < (mode === 'answer' ? 0.22 : 0.4)
        ? {
            rating: 'down',
            reason: ['wrong', 'insufficient', 'irrelevant', null][Math.floor(random() * 4)],
            updated_at: finishedAt,
          }
        : null;
  return {
    ...base,
    status: 'completed',
    mode,
    answer,
    show_contact: mode === 'partial' || mode === 'unknown' || supportNeeded,
    reason,
    error_code: null,
    latency_ms: latency,
    // 측정하지 못한 경우(null)도 섞는다
    prompt_tokens: random() < 0.05 ? null : Math.round(2400 + random() * 600),
    completion_tokens: random() < 0.05 ? null : Math.round(60 + random() * 160),
    retrieved_sources: sources(retrievedIds, random),
    cited_sources: sources(citedIds, random, true),
    feedback,
  };
}

const NAMES = [
  '김O진',
  '박O현',
  '이O수',
  '최O아',
  '정O우',
  '한O린',
  '윤O서',
  '장O민',
  '오O준',
  '서O윤',
];
const INQUIRY_TEXT = {
  uncertain_answer_card: [
    '한쪽 귀마개를 잃어버렸어요. 따로 살 수 있는지, 가격이 얼마인지 알고 싶어요.',
    '충전 케이스 표시등이 계속 깜빡여요. 불량인지 확인 부탁드려요.',
    '중이염 치료 중인데 사용해도 되는지 직접 확인받고 싶어요.',
  ],
  agent_request: [
    '상담사와 직접 이야기하고 싶어요. 연락 부탁드립니다.',
    '구매 전에 몇 가지 더 여쭤보고 싶어요.',
  ],
  direct_form: [
    '회사 복지용으로 30개 정도 단체 구매를 생각하고 있어요. 견적 받을 수 있을까요?',
    '어제 주문했는데 배송지를 바꾸고 싶어요.',
    '선물 포장이 가능한지 궁금해요.',
  ],
};

export function createMockData(now = Date.now()) {
  const random = seededRandom(20261113);
  const turns = [];
  const chats = [];
  const DAY = 24 * 60 * 60 * 1000;

  // 최근 14일 동안의 대화. 최근일수록 조금 더 많다
  for (let day = 13; day >= 0; day -= 1) {
    const chatCount = 3 + Math.floor(random() * 4) + (day < 7 ? 2 : 0);
    for (let c = 0; c < chatCount; c += 1) {
      const chatId = uuid(random);
      const start = now - day * DAY - Math.floor(random() * 20 * 60 * 60 * 1000) - 60 * 60 * 1000;
      const chatTurns = [];
      const length = 1 + Math.floor(random() * 3);
      let parent = null;
      for (let t = 0; t < length; t += 1) {
        const scenario = SCENARIOS[Math.floor(random() * SCENARIOS.length)];
        const createdAt = new Date(start + t * 90_000).toISOString();
        const turn = makeTurn(random, chatId, parent?.turn_id ?? null, scenario, createdAt);
        chatTurns.push(turn);
        // 실패 turn은 부모가 될 수 없다
        if (turn.status === 'completed') parent = turn;
      }
      turns.push(...chatTurns);
      chats.push({ id: chatId, turns: chatTurns });
    }
  }

  // 문의: 문의 카드가 뜬 답변, 상담사 연결, 대화 없는 직접 문의를 섞는다
  const inquiries = [];
  let referenceNo = 1001;
  const addInquiry = (origin, chat, trigger, createdAt, index) => {
    const lastSaved = chat ? chat.turns.filter((t) => t.finished_at <= createdAt).at(-1) : null;
    const status = ['received', 'received', 'in_progress', 'completed'][index % 4];
    const viewed = status !== 'received' || index % 3 === 0;
    inquiries.push({
      id: uuid(random),
      reference_no: `INQ-${referenceNo++}`,
      name: NAMES[index % NAMES.length],
      email: `customer${index + 1}@example.com`,
      content: INQUIRY_TEXT[origin][index % INQUIRY_TEXT[origin].length],
      origin,
      status,
      internal_note: status === 'received' ? '' : '구매처 확인 요청함. 회신 대기 중',
      chat_id: chat?.id ?? null,
      trigger_turn_id: trigger?.turn_id ?? null,
      context_last_turn_id: lastSaved?.turn_id ?? null,
      first_viewed_at: viewed ? createdAt : null,
      completed_at: status === 'completed' ? createdAt : null,
      created_at: createdAt,
      updated_at: createdAt,
    });
  };

  let index = 0;
  chats
    .slice()
    .reverse()
    .forEach((chat) => {
      if (inquiries.length >= 10) return;
      const card = chat.turns.find((t) => t.status === 'completed' && t.show_contact);
      if (card && index % 2 === 0) {
        const at = new Date(new Date(card.finished_at).getTime() + 60_000).toISOString();
        addInquiry('uncertain_answer_card', chat, card, at, index);
      } else if (index % 5 === 1) {
        const last = chat.turns.filter((t) => t.status === 'completed').at(-1);
        const at = new Date(
          new Date(chat.turns.at(-1).finished_at).getTime() + 30_000,
        ).toISOString();
        addInquiry('agent_request', chat, last ?? null, at, index);
      }
      index += 1;
    });
  for (let i = 0; i < 3; i += 1) {
    const at = new Date(now - (i * 2 + 1) * DAY + 3 * 60 * 60 * 1000).toISOString();
    addInquiry('direct_form', null, null, at, i + 20);
  }
  inquiries.sort((a, b) => b.created_at.localeCompare(a.created_at));

  return { turns, inquiries };
}
