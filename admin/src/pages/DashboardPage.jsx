import { useState } from 'react';
import { api } from '../api/client';
import Icon from '../components/Icon';
import { PageHead } from '../components/Layout';
import State from '../components/State';
import { useAsync } from '../hooks/useAsync';
import {
  ERROR_CODE_LABEL,
  MODE_LABEL,
  formatRatio,
  formatSeconds,
  formatUsd,
  periodRange,
} from '../lib/format';

const RANGES = [
  { value: '7', label: '최근 7일' },
  { value: '14', label: '최근 14일' },
  { value: '30', label: '최근 30일' },
];
const TONE = {
  crit: 'tone-crit',
  primary: 'tone-info',
  warn: 'tone-warn',
  ok: 'tone-ok',
};

function Kpi({ icon, tone, label, value, unit, hint }) {
  return (
    <div className="card kpi">
      <span className={`ico ${TONE[tone]}`}>
        <Icon name={icon} />
      </span>
      <div className="txt">
        <span className="label">{label}</span>
        <span className="val">
          {value}
          {unit && <small>{unit}</small>}
        </span>
        {hint && <span className="hint">{hint}</span>}
      </div>
    </div>
  );
}

function DailyChart({ days }) {
  const W = 560;
  const H = 220;
  const L = 32;
  const R = 8;
  const T = 16;
  const B = 26;
  const top = Math.max(4, ...days.map((d) => d.count));
  const step = Math.ceil(top / 4);
  const yMax = step * 4;
  const innerW = W - L - R;
  const innerH = H - T - B;
  const barW = innerW / days.length;
  const y = (value) => T + innerH - (value / yMax) * innerH;
  // 날짜가 많으면 라벨을 건너뛰어 겹치지 않게 한다
  const labelEvery = Math.ceil(days.length / 10);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`일별 질문 수, 최대 ${top}건`}>
      {[0, 1, 2, 3, 4].map((i) => (
        <g key={i}>
          <line className="grid" x1={L} x2={W - R} y1={y(i * step)} y2={y(i * step)} />
          <text className="axis" x={L - 6} y={y(i * step) + 4} textAnchor="end">
            {i * step}
          </text>
        </g>
      ))}
      {days.map((day, i) => {
        const x = L + i * barW + barW * 0.2;
        const w = barW * 0.6;
        const isLast = i === days.length - 1;
        return (
          <g key={day.date}>
            <rect
              className={`bar ${isLast ? 'last' : ''}`}
              x={x}
              y={y(day.count)}
              width={w}
              height={y(0) - y(day.count)}
              rx="3"
            >
              <title>{`${day.date} ${day.count}건`}</title>
            </rect>
            {days.length <= 14 && (
              <text className="val" x={x + w / 2} y={y(day.count) - 5} textAnchor="middle">
                {day.count}
              </text>
            )}
            {i % labelEvery === 0 && (
              <text className="axis" x={x + w / 2} y={H - 8} textAnchor="middle">
                {day.date.slice(5).replace('-', '/')}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export default function DashboardPage({ navigate }) {
  const [days, setDays] = useState('7');
  const data = useAsync(() => api.dashboard(periodRange(Number(days))), days);
  const d = data.data;

  return (
    <>
      <PageHead title="대시보드" description="챗봇 사용 현황이에요. 날짜는 한국 시간 기준이에요.">
        <div className="seg" role="group" aria-label="기간">
          {RANGES.map((range) => (
            <button
              key={range.value}
              type="button"
              aria-pressed={days === range.value}
              onClick={() => setDays(range.value)}
            >
              {range.label}
            </button>
          ))}
        </div>
      </PageHead>
      <State isLoading={data.isLoading} error={data.error} isEmpty={!d} onRetry={data.reload}>
        {d && (
          <>
            <div className="kpis">
              <Kpi
                icon="inbox"
                tone="crit"
                label="처리 안 된 문의"
                value={d.unresolved_inquiry_count}
                unit="건"
                hint={
                  <>
                    전체 기간 · 확인 안 함 {d.unread_inquiry_count}건 ·{' '}
                    <button type="button" className="link" onClick={() => navigate('inquiries')}>
                      확인하기
                    </button>
                  </>
                }
              />
              <Kpi
                icon="msg"
                tone="primary"
                label="질문 수"
                value={d.question_count}
                unit="건"
                hint={`실패 ${d.failed_count}건 포함`}
              />
              <Kpi
                icon="clock"
                tone="primary"
                label="평균 응답 시간"
                value={formatSeconds(d.average_latency_ms)}
                hint="완료된 질문 기준"
              />
              <Kpi
                icon="help"
                tone="warn"
                label="불확실 답변 비율"
                value={formatRatio(d.uncertain_ratio)}
                hint={`부분 답변 ${d.mode_counts.partial} · 답변 불가 ${d.mode_counts.unknown}`}
              />
              <Kpi
                icon="thumb"
                tone="ok"
                label="👍 비율"
                value={formatRatio(d.positive_feedback_ratio)}
                hint={`피드백 ${d.feedback_count}건 중`}
              />
              <Kpi
                icon="coin"
                tone="primary"
                label="예상 비용"
                value={formatUsd(d.estimated_cost_usd, 3)}
                hint={`질문당 ${formatUsd(d.average_cost_usd, 5)} · 가정 단가 기준`}
              />
            </div>
            <div className="dash-grid">
              <section className="card chart">
                <div className="card-head">
                  <h2>일별 질문 수</h2>
                  <span className="sub">완료 + 실패</span>
                </div>
                <div className="card-body">
                  <DailyChart days={d.daily_questions} />
                </div>
              </section>
              <section className="card">
                <div className="card-head">
                  <h2>많이 참고된 FAQ</h2>
                  <span className="sub">답변 근거 기준</span>
                </div>
                <div className="card-body">
                  {d.top_sources.length ? (
                    <ol className="rank">
                      {d.top_sources.map((source) => (
                        <li key={source.source_id}>
                          <span className="fid">{source.source_id}</span>
                          <span className="t" title={source.title ?? ''}>
                            {source.title ?? '(제목 없음)'}
                          </span>
                          <span className="num">{source.count}</span>
                          <span className="track">
                            <svg width="100%" height="4" aria-hidden="true">
                              <rect
                                className="mini-bar"
                                width={`${(source.count / d.top_sources[0].count) * 100}%`}
                                height="4"
                                rx="2"
                              />
                            </svg>
                          </span>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="note">이 기간에 답변 근거로 쓰인 FAQ가 없어요.</p>
                  )}
                </div>
              </section>
            </div>
            <section className="card">
              <div className="card-head">
                <h2>판단과 실패 원인</h2>
              </div>
              <div className="card-body sec">
                <div className="breakdown">
                  {Object.entries(d.mode_counts).map(([mode, count]) => (
                    <span key={mode} className="badge tone-muted">
                      {MODE_LABEL[mode]} {count}
                    </span>
                  ))}
                </div>
                {Object.keys(d.failed_by_reason).length ? (
                  <div className="breakdown">
                    {Object.entries(d.failed_by_reason).map(([code, count]) => (
                      <span key={code} className="badge tone-crit">
                        <Icon name="warning" /> {ERROR_CODE_LABEL[code] ?? code} {count}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="note">이 기간에 시스템 오류로 실패한 질문이 없어요.</p>
                )}
                <p className="note">
                  크레딧 소진처럼 계속되는 장애는 실패 원인에서 먼저 보여요. 비용은 LLM 토큰만
                  계산한 예상치예요.
                </p>
              </div>
            </section>
          </>
        )}
      </State>
    </>
  );
}
