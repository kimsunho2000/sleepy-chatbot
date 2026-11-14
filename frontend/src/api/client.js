// 백엔드 API 호출은 이 파일에만 둔다. 계약은 Swagger(https://sleepy-team.github.io/sleepy-chatbot/)를 따른다.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// 데모 빌드는 백엔드 대신 브라우저 안의 간단한 엔진을 쓴다 (정적 치환이라 일반 빌드에는 포함되지 않는다)
const IS_DEMO = import.meta.env.VITE_DEMO === 'true';
const loadDemo = () => import('./demoEngine');

// 서버가 돌려준 오류. code는 Swagger의 error.code 값이고, 연결 자체가 안 되면 network_error다
export class ApiError extends Error {
  constructor(status, code, message, { retryAfter = null, turnId = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
    this.turnId = turnId;
  }
}

async function request(path, { token, ...options } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  } catch {
    throw new ApiError(0, 'network_error', '서버와 연결하지 못했어요.');
  }
  if (response.ok) return response.status === 204 ? null : response.json();

  const body = await response.json().catch(() => null);
  const retryAfter = Number(response.headers.get('Retry-After'));
  throw new ApiError(
    response.status,
    body?.error?.code ?? 'unknown_error',
    body?.error?.message ?? `요청에 실패했어요 (${response.status})`,
    { retryAfter: retryAfter > 0 ? retryAfter : null, turnId: body?.turn_id ?? null },
  );
}

// 새 대화를 만들고 대화 토큰을 받는다. 초기화도 새 대화를 만드는 것이다
export async function createChat() {
  if (IS_DEMO) return (await loadDemo()).demoCreateChat();
  return request('/api/chats', { method: 'POST' });
}

// 질문 1건을 보내고 답변 1건(TurnResponse)을 받는다
export async function sendTurn({ chatId, token, question, parentTurnId }) {
  if (IS_DEMO) return (await loadDemo()).demoTurn({ chatId, question, parentTurnId });
  return request(`/api/chats/${chatId}/turns`, {
    method: 'POST',
    token,
    body: JSON.stringify({ question, parent_turn_id: parentTurnId ?? null }),
  });
}

// 답변 평가 등록·교체. reason은 👎일 때만 보낸다 (wrong | insufficient | irrelevant)
export async function putFeedback({ chatId, token, turnId, rating, reason }) {
  if (IS_DEMO) return (await loadDemo()).demoFeedback({ rating, reason });
  const body = rating === 'down' && reason ? { rating, reason } : { rating };
  return request(`/api/chats/${chatId}/turns/${turnId}/feedback`, {
    method: 'PUT',
    token,
    body: JSON.stringify(body),
  });
}

// 답변 평가 취소
export async function deleteFeedback({ chatId, token, turnId }) {
  if (IS_DEMO) return null;
  return request(`/api/chats/${chatId}/turns/${turnId}/feedback`, { method: 'DELETE', token });
}

// 문의 접수. 대화가 있으면 그 대화의 토큰을 함께 보낸다
export async function sendInquiry(payload, token) {
  if (IS_DEMO) return (await loadDemo()).demoInquiry(payload);
  return request('/api/inquiries', { method: 'POST', token, body: JSON.stringify(payload) });
}
