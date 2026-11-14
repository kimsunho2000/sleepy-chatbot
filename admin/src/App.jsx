import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';
import Layout from './components/Layout';
import { useAuth } from './hooks/useAuth';
import { useHashRoute } from './hooks/useHashRoute';
import { useTheme } from './hooks/useTheme';
import { useToast } from './hooks/useToast';
import DashboardPage from './pages/DashboardPage';
import InquiriesPage from './pages/InquiriesPage';
import LoginPage from './pages/LoginPage';
import LogsPage from './pages/LogsPage';
import UnansweredPage from './pages/UnansweredPage';

export default function App() {
  const auth = useAuth();
  const theme = useTheme();
  const toast = useToast();
  const route = useHashRoute();
  const [unreadCount, setUnreadCount] = useState(0);

  // 상단 알림 배지는 필터 없이 센 미확인 문의 수다
  const refreshUnread = useCallback(() => {
    api
      .inquiryCounts()
      .then((counts) => setUnreadCount(counts.unread))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (auth.status === 'signed-in') refreshUnread();
  }, [auth.status, refreshUnread]);

  if (auth.status === 'checking') return <div className="state">로그인 상태를 확인하는 중…</div>;
  if (auth.status !== 'signed-in') return <LoginPage auth={auth} />;

  const pageProps = { params: route.params, navigate: route.navigate, toast: toast.show };
  const page = {
    inquiries: <InquiriesPage {...pageProps} onChanged={refreshUnread} />,
    unanswered: <UnansweredPage {...pageProps} />,
    logs: <LogsPage key={route.params.chat_id ?? 'all'} {...pageProps} />,
    dashboard: <DashboardPage {...pageProps} />,
  }[route.page];

  return (
    <>
      <Layout
        page={route.page}
        admin={auth.admin}
        unreadCount={unreadCount}
        theme={theme}
        onSignOut={auth.signOut}
      >
        {page}
      </Layout>
      {toast.message && (
        <div className="toast" role="status">
          {toast.message}
        </div>
      )}
    </>
  );
}
