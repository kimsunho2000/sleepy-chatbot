import { useCallback, useEffect, useRef, useState } from 'react';
import ChatPanel from './components/ChatPanel';
import Icon from './components/Icon';
import Landing from './landing/Landing';

const CHAT_ID = 'sleeby-chat';
const isSoloHash = () => window.location.hash === '#/chat';

export default function App() {
  const [isOpen, setIsOpen] = useState(false);
  const [isSolo, setIsSolo] = useState(isSoloHash());
  // 랜딩 페이지에서 고른 질문. 챗봇을 열면서 바로 보낸다
  const [pendingQuestion, setPendingQuestion] = useState(null);
  const launcherRef = useRef(null);
  const wasOpenRef = useRef(false);

  useEffect(() => {
    const onHashChange = () => setIsSolo(isSoloHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  // 창을 닫으면 포커스를 런처로 돌려준다
  useEffect(() => {
    if (wasOpenRef.current && !isOpen) launcherRef.current?.focus();
    wasOpenRef.current = isOpen;
  }, [isOpen]);

  const closeChat = useCallback(() => setIsOpen(false), []);

  if (isSolo) {
    return <ChatPanel isSolo onClose={() => (window.location.hash = '#/')} />;
  }

  const askFromPage = (question) => {
    setIsOpen(true);
    setPendingQuestion({ id: crypto.randomUUID(), text: question });
  };

  return (
    <>
      <Landing onAsk={askFromPage} onOpenChat={() => setIsOpen(true)} />
      <button
        ref={launcherRef}
        type="button"
        className="launcher"
        hidden={isOpen}
        aria-controls={CHAT_ID}
        aria-expanded={isOpen}
        onClick={() => setIsOpen(true)}
      >
        <span className="dot" aria-hidden="true">
          <Icon name="moon" />
        </span>
        안내 도우미
      </button>
      {/* 닫아도 대화가 남도록 숨기기만 한다 */}
      <div hidden={!isOpen}>
        <ChatPanel
          id={CHAT_ID}
          isOpen={isOpen}
          pendingQuestion={pendingQuestion}
          onClose={closeChat}
        />
      </div>
    </>
  );
}
