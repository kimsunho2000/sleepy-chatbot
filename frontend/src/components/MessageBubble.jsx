import { useState } from 'react';
import InquiryForm from './InquiryForm';
import SourceChips from './SourceChips';

const MODE_LABEL = {
  partial: '일부만 확인된 답변이에요',
  unknown: '자료에서 확인되지 않았어요',
  offtopic: '답변 범위 밖의 질문이에요',
  error: '연결 오류',
};

// 근거로 답한 경우에만 출처 칩을 보여 준다 (인사·범위 밖·되묻기·확인 불가에는 숨긴다)
const HAS_SOURCES_MODES = ['answer', 'partial'];

export default function MessageBubble({ message, sessionId }) {
  const [isFormOpen, setIsFormOpen] = useState(false);

  if (message.role === 'user') {
    return <div className="msg user">{message.text}</div>;
  }

  // 답변이 배지와 같은 문구로 시작하면 배지를 숨겨 같은 말이 두 번 보이지 않게 한다
  const modeLabel = MODE_LABEL[message.mode];
  const label = modeLabel && !message.text.trim().startsWith(modeLabel) ? modeLabel : null;
  return (
    <div className={`msg bot mode-${message.mode}`}>
      <span className="av" aria-hidden="true">
        ☾
      </span>
      <div className="bot-text">
        {label && <span className="mode-label">{label}</span>}
        <p>{message.text}</p>
        {HAS_SOURCES_MODES.includes(message.mode) && <SourceChips sources={message.sources} />}
        {message.needs_inquiry && !isFormOpen && (
          <div className="chips">
            <button type="button" className="pill solid" onClick={() => setIsFormOpen(true)}>
              담당자에게 문의하기
            </button>
          </div>
        )}
        {isFormOpen && (
          <InquiryForm sessionId={sessionId.current} onClose={() => setIsFormOpen(false)} />
        )}
      </div>
    </div>
  );
}
