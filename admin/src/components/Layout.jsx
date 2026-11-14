import { isMock } from '../api/client';
import Icon from './Icon';
import ThemeToggle from './ThemeToggle';

const MENU = [
  { page: 'inquiries', label: '문의 관리', icon: 'inbox' },
  { page: 'unanswered', label: '답 못 한 질문', icon: 'alert' },
  { page: 'logs', label: '질문 로그', icon: 'list' },
  { page: 'dashboard', label: '대시보드', icon: 'chart' },
];

const PAGE_TITLE = Object.fromEntries(MENU.map((item) => [item.page, item.label]));

export default function Layout({ page, admin, unreadCount, theme, onSignOut, children }) {
  return (
    <div className="app">
      <aside className="side">
        {/* 로그인 화면·고객 챗봇과 같은 SLEEPY 글자 로고 */}
        <div className="brand">
          <span className="brand-moon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
            </svg>
          </span>
          <div>
            <b className="brand-wordmark">SLEEPY</b>
            <span>슬리비 상담 관리</span>
          </div>
        </div>
        <div className="nav-label">운영</div>
        <nav className="nav" aria-label="관리 메뉴">
          {MENU.map((item) => (
            <a
              key={item.page}
              href={`#/${item.page}`}
              aria-current={page === item.page ? 'page' : undefined}
            >
              <Icon name={item.icon} />
              <span className="grow">{item.label}</span>
              {item.page === 'inquiries' && unreadCount > 0 && (
                <span className="count" title="확인 안 한 문의">
                  {unreadCount}
                </span>
              )}
            </a>
          ))}
        </nav>
      </aside>
      <div className="wrap">
        <header className="topbar">
          <div className="crumb">
            <span>홈</span>
            <span>/</span>
            <b>{PAGE_TITLE[page]}</b>
          </div>
          <div className="top-right">
            <ThemeToggle theme={theme} />
            <a className="bell" href="#/inquiries" aria-label={`확인 안 한 문의 ${unreadCount}건`}>
              <Icon name="bell" />
              {unreadCount > 0 && <span className="count">{unreadCount}</span>}
            </a>
            <div className="user">
              <span className="avatar" aria-hidden="true">
                {admin?.display_name?.[0] ?? '관'}
              </span>
              <span className="name">{admin?.display_name}</span>
              <button type="button" className="ghost-btn" onClick={() => onSignOut()}>
                로그아웃
              </button>
            </div>
          </div>
        </header>
        <main className="main">
          {isMock && (
            <div className="mock-bar">
              <b>목 데이터</b>
              <span>
                백엔드 없이 명세 모양의 가짜 데이터로 보여 줘요. 새로고침하면 바꾼 내용이 처음으로
                돌아가요.
              </span>
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}

export function PageHead({ title, description, children }) {
  return (
    <div className="head">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </div>
  );
}
