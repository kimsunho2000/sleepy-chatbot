import { useState } from 'react';

// 점수는 개발 모드(VITE_SHOW_SCORE=true)에서만 보여 준다
const SHOULD_SHOW_SCORE = import.meta.env.VITE_SHOW_SCORE === 'true';

// 같은 출처 라벨(예: 제품소개서 청크 여러 개)은 칩 하나로 합친다
function uniqueByLabel(sources) {
  const seen = new Set();
  return sources.filter((source) => {
    if (seen.has(source.label)) return false;
    seen.add(source.label);
    return true;
  });
}

export default function SourceChips({ sources }) {
  const [openIndex, setOpenIndex] = useState(null);
  if (!sources?.length) return null;
  const chips = uniqueByLabel(sources);
  const current = openIndex === null ? null : chips[openIndex];

  return (
    <div className="sources">
      <span className="src">참고한 자료</span>
      <div className="chips">
        {chips.map((source, index) => (
          <button
            key={`${source.label}-${index}`}
            type="button"
            className={`pill ${openIndex === index ? 'is-on' : ''}`}
            onClick={() => setOpenIndex(openIndex === index ? null : index)}
          >
            <span className="pill-label">{source.label}</span>
            {SHOULD_SHOW_SCORE && source.score != null && (
              <span className="score">유사도 {source.score.toFixed(2)}</span>
            )}
          </button>
        ))}
      </div>
      {current && (
        <div className="excerpt">
          <strong>{current.title}</strong>
          <p>{current.excerpt}</p>
        </div>
      )}
    </div>
  );
}
