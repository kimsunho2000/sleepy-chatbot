// 관리자 API 호출은 이 파일에만 둔다. 계약은 Swagger(https://sleepy-team.github.io/sleepy-chatbot/)를 따른다.
// 운영 빌드에서 주소를 빠뜨리면 localhost로 조용히 붙지 않고 바로 드러나게 한다
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : null);
// npm run mock: 백엔드 없이 명세 모양의 가짜 데이터로 동작한다 (정적 치환이라 일반 빌드에는 포함되지 않는다)
const IS_MOCK = import.meta.env.VITE_MOCK === 'true';
const loadMock = () => import('./mock/mockServer');

export class ApiError extends Error {
  // retryAfter: 서버가 Retry-After로 알려 준 대기 초 (없으면 null)
  constructor(status, code, message, retryAfter = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

let token = null;
let onUnauthorized = () => {};

export function setToken(value) {
  token = value;
}

// 토큰이 만료되면 로그인 화면으로 돌려보내도록 App이 등록한다
export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

function query(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : '';
}

// 보낼 때의 토큰이 지금도 쓰는 토큰일 때만 로그아웃한다.
// 다시 로그인한 뒤에 이전 토큰으로 보낸 요청의 401이 늦게 와도 새 세션을 끊지 않는다
function handleUnauthorized(sentToken) {
  if (sentToken && sentToken === token) onUnauthorized();
}

async function request(method, path, { params, body } = {}) {
  const url = `${path}${query(params)}`;
  const sentToken = token;
  if (IS_MOCK) {
    const mock = await loadMock();
    try {
      return await mock.handle(method, url, body, sentToken);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) handleUnauthorized(sentToken);
      throw error;
    }
  }
  if (!API_BASE_URL) {
    throw new ApiError(0, 'config_error', 'API 주소(VITE_API_BASE_URL)가 설정되지 않았어요.');
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${url}`, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(sentToken ? { Authorization: `Bearer ${sentToken}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'network_error', '서버와 연결하지 못했어요.');
  }
  if (response.ok) return response.status === 204 ? null : response.json();

  const data = await response.json().catch(() => null);
  const retryAfter = Number(response.headers.get('Retry-After'));
  const error = new ApiError(
    response.status,
    data?.error?.code ?? 'unknown_error',
    data?.error?.message ?? `요청에 실패했어요 (${response.status})`,
    retryAfter > 0 ? retryAfter : null,
  );
  if (response.status === 401) handleUnauthorized(sentToken);
  throw error;
}

export const api = {
  login: (username, password) =>
    request('POST', '/api/admin/tokens', { body: { username, password } }),
  currentToken: () => request('GET', '/api/admin/tokens/current'),

  listInquiries: (params) => request('GET', '/api/admin/inquiries', { params }),
  inquiryCounts: (params) => request('GET', '/api/admin/inquiry-counts', { params }),
  getInquiry: (id) => request('GET', `/api/admin/inquiries/${id}`),
  updateInquiry: (id, patch) => request('PATCH', `/api/admin/inquiries/${id}`, { body: patch }),

  listTurns: (params) => request('GET', '/api/admin/turns', { params }),
  getTurn: (id) => request('GET', `/api/admin/turns/${id}`),

  listUnansweredGroups: (params) => request('GET', '/api/admin/unanswered-groups', { params }),
  getUnansweredGroup: (key, params) =>
    request('GET', `/api/admin/unanswered-groups/${encodeURIComponent(key)}`, { params }),

  dashboard: (params) => request('GET', '/api/admin/dashboard', { params }),
};

export const isMock = IS_MOCK;
