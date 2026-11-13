const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`요청에 실패했어요 (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

// 데모 빌드는 백엔드 대신 브라우저 안의 간단한 엔진을 쓴다 (정적 치환이라 일반 빌드에는 포함되지 않는다)
const IS_DEMO = import.meta.env.VITE_DEMO === 'true';

export async function sendChat(message, sessionId, signal) {
  if (IS_DEMO) return (await import('./demoEngine')).demoChat(message, sessionId, signal);
  return request('/api/chats', {
    method: 'POST',
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  });
}

export async function resetChat(sessionId) {
  if (IS_DEMO) return (await import('./demoEngine')).demoReset();
  return request(`/api/chats/${sessionId}`, { method: 'DELETE' });
}

export async function sendInquiry(payload) {
  if (IS_DEMO) return (await import('./demoEngine')).demoInquiry();
  return request('/api/inquiries', { method: 'POST', body: JSON.stringify(payload) });
}
