import { formatScore } from '../lib/format';
import { ModeBadge } from './Badges';

function SourceChips({ label, sources }) {
  if (!sources.length) return null;
  return (
    <span className="meta">
      <span className="sub">{label}</span>
      {sources.map((source) => (
        <span key={source.source_id} className="ref" title={source.title ?? ''}>
          <b>{source.source_id}</b> {source.title ?? '(제목 없음)'}{' '}
          <span className="num">{formatScore(source.score)}</span>
        </span>
      ))}
    </span>
  );
}

// 문의 상세의 채팅 기록. 답변 근거(cited)와 검색 후보 상위 3개(retrieved)를 함께 보여 준다
export default function Conversation({ turns }) {
  const seenParents = new Set();
  return (
    <div className="chat">
      {turns.map((turn) => {
        // 같은 부모에서 다시 나온 turn은 다시 답변받기·질문 수정·실패 후 재질문 중 하나다
        const parentKey = turn.parent_turn_id ?? 'root';
        const isBranch = seenParents.has(parentKey);
        seenParents.add(parentKey);
        return (
          <div key={turn.turn_id} className="chat-turn">
            {isBranch && <div className="branch">↳ 분기된 답변 시도</div>}
            <div className="bubble user">{turn.question}</div>
            <div className={`bubble bot ${turn.is_trigger ? 'trigger' : ''}`}>
              {turn.status === 'failed' ? (
                <span className="sub">답변을 만들지 못했어요 (시스템 오류)</span>
              ) : (
                <span>{turn.answer}</span>
              )}
              <span className="meta">
                <ModeBadge status={turn.status} mode={turn.mode} />
                {turn.is_trigger && <span className="badge tone-warn">이 답변에서 문의 접수</span>}
              </span>
              <SourceChips label="근거" sources={turn.cited_sources} />
              <SourceChips label="검색 후보" sources={turn.retrieved_sources} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
