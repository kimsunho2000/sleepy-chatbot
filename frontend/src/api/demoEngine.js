// 데모 빌드(VITE_DEMO=true) 전용: 백엔드 없이 브라우저에서 FAQ·제품 JSON을 글자 겹침으로 찾아 답한다.
// 실제 서비스의 RAG(검색 + LLM)가 아니라 화면과 흐름을 확인하기 위한 간단한 대체 엔진이다.
import faq from '../../../data/faq.json';
import product from '../../../data/product.json';

const ANSWER_THRESHOLD = 0.45;
const PARTIAL_THRESHOLD = 0.25;
const GREETING_PATTERN = /^(안녕|하이|hello|hi)/i;

const ITEMS = [...faq, ...product].filter((item) => item.answer && item.status !== 'draft');

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

const labelOf = (item) =>
  item.faq_id.startsWith('P') ? `제품 정보 ${item.faq_id}` : `FAQ ${item.faq_id}`;

const toSource = ({ item }, score) => ({
  faq_id: item.faq_id,
  label: labelOf(item),
  title: item.question,
  category: item.category,
  score,
  excerpt: item.answer,
});

const wait = (ms, signal) =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(new DOMException('aborted', 'AbortError'));
    });
  });

export async function demoChat(message, sessionId, signal) {
  await wait(600, signal);
  const base = { session_id: sessionId ?? 'demo-session', sources: [], needs_inquiry: false };
  const query = bigrams(message);

  if (GREETING_PATTERN.test(message.trim()) && query.size <= 6) {
    return {
      ...base,
      mode: 'chitchat',
      answer: '안녕하세요! 슬리비에 대해 궁금한 점을 물어보세요.',
    };
  }

  const ranked = INDEX.map((entry) => {
    let hit = 0;
    query.forEach((gram) => {
      if (entry.grams.has(gram)) hit += 1;
    });
    return { entry, score: query.size ? hit / query.size : 0 };
  }).sort((a, b) => b.score - a.score);

  const best = ranked[0];
  if (!best || best.score < PARTIAL_THRESHOLD) {
    return {
      ...base,
      mode: 'unknown',
      answer: '질문하신 내용은 제가 가진 자료에서 확인하지 못했어요. 담당자에게 문의해 주세요.',
      needs_inquiry: true,
    };
  }
  return {
    ...base,
    mode: best.score >= ANSWER_THRESHOLD ? 'answer' : 'partial',
    answer: best.entry.item.answer,
    sources: [toSource(best.entry, best.score)],
    needs_inquiry: best.entry.item.support_required === true,
  };
}

export async function demoReset() {
  return null;
}

export async function demoInquiry() {
  await wait(500);
  return { status: 'received' };
}
