import { useState } from 'react';

const ERROR_TEXT = {
  unauthorized: '아이디 또는 비밀번호가 올바르지 않아요.',
  rate_limited: '로그인 시도가 많아 잠시 막혔어요. 조금 뒤에 다시 시도해 주세요.',
  network_error: '서버와 연결하지 못했어요.',
};

// 챗봇 홈페이지와 같은 밤 분위기(월넛 바닥, 리넨 글자, 스탠드 조명)로 맞춘다
export default function LoginPage({ auth }) {
  const [form, setForm] = useState({ username: '', password: '' });
  const [error, setError] = useState(auth.notice);
  const [isSending, setIsSending] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    if (!form.username.trim() || !form.password) {
      setError('아이디와 비밀번호를 모두 입력하세요.');
      return;
    }
    setIsSending(true);
    setError('');
    try {
      await auth.signIn(form.username.trim(), form.password);
    } catch (caught) {
      const wait = caught.code === 'rate_limited' && caught.retryAfter;
      setError(
        wait
          ? `로그인 시도가 많아 잠시 막혔어요. 약 ${Math.ceil(wait / 60)}분 뒤에 다시 시도해 주세요.`
          : (ERROR_TEXT[caught.code] ?? '로그인하지 못했어요. 잠시 후 다시 시도해 주세요.'),
      );
      setIsSending(false);
    }
  };

  const update = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));
  // 만료·연결 안내는 입력값 문제가 아니므로 입력 칸을 오류로 표시하지 않는다
  const isInvalid = Boolean(error) && error !== auth.notice && !isSending;

  return (
    <div className="login">
      <div className="login-glow" aria-hidden="true" />
      <div className="login-box">
        <header className="login-head">
          <span className="login-moon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
            </svg>
          </span>
          <span className="login-wordmark">SLEEPY</span>
          <span className="login-sub">슬리비 상담 관리</span>
        </header>
        <form className="login-card" noValidate onSubmit={submit}>
          <div>
            <h1>관리자 로그인</h1>
            <p>챗봇 문의와 대화 기록을 확인하는 운영 화면이에요.</p>
          </div>
          <div className="login-field">
            <label htmlFor="login-id">아이디</label>
            <input
              id="login-id"
              autoComplete="username"
              autoFocus
              aria-invalid={isInvalid}
              value={form.username}
              onChange={update('username')}
            />
          </div>
          <div className="login-field">
            <label htmlFor="login-pw">비밀번호</label>
            <input
              id="login-pw"
              type="password"
              autoComplete="current-password"
              aria-invalid={isInvalid}
              value={form.password}
              onChange={update('password')}
            />
          </div>
          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="login-submit" disabled={isSending}>
            {isSending ? '로그인 중…' : '로그인'}
          </button>
        </form>
        <p className="login-foot">관리자 계정은 담당자에게 받아 주세요.</p>
      </div>
    </div>
  );
}
