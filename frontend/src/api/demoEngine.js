// 데모 빌드(VITE_DEMO=true) 전용: 백엔드 없이 브라우저에서 FAQ·제품 JSON을 글자 겹침으로 찾아 답한다.
// 실제 서비스의 RAG(검색 + LLM)가 아니라 화면과 흐름을 확인하기 위한 간단한 대체 엔진이다.
// 응답 모양은 Swagger의 실제 API와 같게 맞춘다 (출처는 고객 응답에 넣지 않는다).
import faq from '../../../data/faq.json';
import product from '../../../data/product.json';

const ANSWER_THRESHOLD = 0.45;
const PARTIAL_THRESHOLD = 0.25;
const GREETING_PATTERN = /^(안녕|하이|hello|hi|고마워|감사)/i;

const ITEMS = [...faq, ...product].filter((item) => item.answer && item.status === 'confirmed');

const bigrams = (text) => {
  const compact = text.toLowerCase().replace(/[^0-9a-z가-힣]/g, '');
  const grams = new Set();
  for (let i = 0; i < compact.length - 1; i += 1) grams.add(compact.slice(i, i + 2));
  return grams;
};

const INDEX = ITEMS.map((item) => ({
  item,
  grams: bigrams(`${item.question} ${item.question} ${item.answer}`),
}));

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const now = () => new Date().toISOString();

export async function demoCreateChat() {
  return { chat_id: crypto.randomUUID(), chat_token: 'demo-token', created_at: now() };
}

function decide(question) {
  const query = bigrams(question);
  if (GREETING_PATTERN.test(question.trim()) && query.size <= 6) {
    return {
      mode: 'greeting',
      answer:
        '안녕하세요, 슬리비 제품 안내를 돕는 챗봇이에요. 슬리비의 특징, 사용 방법, 유의사항, 구매 방법을 편하게 물어봐 주세요.',
      show_contact: false,
    };
  }
  const best = INDEX.map((entry) => {
    let hit = 0;
    query.forEach((gram) => {
      if (entry.grams.has(gram)) hit += 1;
    });
    return { entry, score: query.size ? hit / query.size : 0 };
  }).sort((a, b) => b.score - a.score)[0];

  if (!best || best.score < PARTIAL_THRESHOLD) {
    return {
      mode: 'unknown',
      answer:
        '죄송해요, 문의하신 내용은 아직 확인된 안내 자료가 없어 정확히 답변드리기 어려워요. 담당자에게 문의해 주시면 확인 후 안내드릴게요.',
      show_contact: true,
    };
  }
  const isAnswer = best.score >= ANSWER_THRESHOLD;
  return {
    mode: isAnswer ? 'answer' : 'partial',
    answer: best.entry.item.answer,
    show_contact: !isAnswer || best.entry.item.support_required === true,
  };
}

export async function demoTurn({ chatId, question, parentTurnId }) {
  await wait(600);
  return {
    turn_id: crypto.randomUUID(),
    chat_id: chatId,
    parent_turn_id: parentTurnId ?? null,
    question,
    ...decide(question),
    feedback: null,
    created_at: now(),
  };
}

export async function demoInquiry() {
  await wait(500);
  return {
    inquiry_id: crypto.randomUUID(),
    reference_no: 'INQ-DEMO',
    status: 'received',
    created_at: now(),
  };
}
