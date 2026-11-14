import { Fragment, useState } from 'react';
import { api } from '../api/client';
import { ModeBadge, RatingMark } from '../components/Badges';
import { PageHead } from '../components/Layout';
import Pager from '../components/Pager';
import State from '../components/State';
import { useAsync } from '../hooks/useAsync';
import { usePageClamp } from '../hooks/usePageClamp';
import {
  ERROR_CODE_LABEL,
  FEEDBACK_REASON_LABEL,
  MODE_LABEL,
  PERIODS,
  formatDateTime,
  formatScore,
  formatSeconds,
  formatUsd,
  periodDays,
  periodRange,
} from '../lib/format';

const PAGE_SIZE = 20;

export default function LogsPage({ params, navigate }) {
  const chatId = params.chat_id ?? '';
  const [filters, setFilters] = useState({ period: '7', mode: '', status: '', rating: '' });
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState(null);

  // 한 대화를 이어 볼 때는 기간과 상관없이 그 대화 전체를 본다
  const range = chatId ? {} : periodRange(periodDays(filters.period));
  const list = useAsync(
    () =>
      api.listTurns({
        ...range,
        mode: filters.mode,
        status: filters.status,
        rating: filters.rating,
        chat_id: chatId,
        page,
        size: PAGE_SIZE,
      }),
    JSON.stringify([filters, page, chatId]),
  );

  const setFilter = (key) => (event) => {
    setFilters((prev) => ({ ...prev, [key]: event.target.value }));
    setPage(1);
  };
  usePageClamp({
    page,
    size: PAGE_SIZE,
    total: list.data?.total_count,
    isLoading: list.isLoading,
    setPage,
  });
  const items = list.data?.items ?? [];

  return (
    <>
      <PageHead
        title="질문 로그"
        description="질문을 누르면 검색된 FAQ, 판단과 사유, 답변, 사용량을 순서대로 볼 수 있어요."
      />
      <section className="card">
        <div className="card-head">
          <h2>{chatId ? '한 대화 이어 보기' : '질문'}</h2>
          <span className="sub num">{list.data ? `${list.data.total_count}건` : ''}</span>
        </div>
        <div className="filters">
          {chatId ? (
            <>
              <span className="badge tone-info">
                대화 <span className="mono">{chatId.slice(0, 8)}</span> · 오래된 순
              </span>
              <button type="button" className="link" onClick={() => navigate('logs')}>
                전체 질문 보기
              </button>
            </>
          ) : (
            <select aria-label="기간" value={filters.period} onChange={setFilter('period')}>
              {PERIODS.map((period) => (
                <option key={period.value} value={period.value}>
                  {period.label}
                </option>
              ))}
            </select>
          )}
          <select aria-label="판단" value={filters.mode} onChange={setFilter('mode')}>
            <option value="">판단 전체</option>
            {Object.entries(MODE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <select aria-label="처리 결과" value={filters.status} onChange={setFilter('status')}>
            <option value="">완료·실패 전체</option>
            <option value="completed">완료</option>
            <option value="failed">실패 (시스템 오류)</option>
          </select>
          <select aria-label="피드백" value={filters.rating} onChange={setFilter('rating')}>
            <option value="">피드백 전체</option>
            <option value="up">👍</option>
            <option value="down">👎</option>
            <option value="none">피드백 없음</option>
          </select>
        </div>
        <State
          isLoading={list.isLoading}
          error={list.error}
          isEmpty={!items.length}
          emptyText="조건에 맞는 질문이 없어요."
          onRetry={list.reload}
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>시각</th>
                  <th>질문</th>
                  <th>판단</th>
                  <th className="r">응답 시간</th>
                  <th>피드백</th>
                </tr>
              </thead>
              <tbody>
                {items.map((turn) => {
                  const isOpen = openId === turn.turn_id;
                  const toggle = () => setOpenId(isOpen ? null : turn.turn_id);
                  return (
                    <Fragment key={turn.turn_id}>
                      <tr
                        className={`click ${isOpen ? 'open' : ''}`}
                        tabIndex={0}
                        aria-expanded={isOpen}
                        onClick={toggle}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            toggle();
                          }
                        }}
                      >
                        <td className="sub num">{formatDateTime(turn.created_at)}</td>
                        <td className="q">{turn.question}</td>
                        <td>
                          <ModeBadge status={turn.status} mode={turn.mode} />
                        </td>
                        <td className="r num">{formatSeconds(turn.latency_ms)}</td>
                        <td>
                          <RatingMark rating={turn.rating} />
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={5} className="detail-cell">
                            <TurnDetail id={turn.turn_id} chatId={chatId} navigate={navigate} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Pager
            page={page}
            size={PAGE_SIZE}
            total={list.data?.total_count ?? 0}
            isLoading={list.isLoading}
            onChange={setPage}
          />
        </State>
      </section>
      <p className="note">
        예상 비용은 LLM 토큰 × 설정 단가로 계산한 값이에요. 임베딩·인프라 비용은 빠져 있어요.
      </p>
    </>
  );
}

function TurnDetail({ id, chatId, navigate }) {
  const detail = useAsync(() => api.getTurn(id), id);
  const turn = detail.data;
  const cited = new Set(turn?.cited_sources.map((source) => source.source_id) ?? []);
  // 후속 질문은 두 검색을 합쳐 근거가 후보 목록 밖에 있을 수 있다. 그때도 근거는 보여 준다
  const retrievedIds = new Set(turn?.retrieved_sources.map((source) => source.source_id) ?? []);
  const citedOnly =
    turn?.cited_sources.filter((source) => !retrievedIds.has(source.source_id)) ?? [];

  return (
    <State
      isLoading={detail.isLoading}
      error={detail.error}
      isEmpty={!turn}
      onRetry={detail.reload}
    >
      {turn && (
        <div className="log-detail">
          <section className="sec">
            <h3>1. 검색된 FAQ</h3>
            {turn.retrieved_sources.length ? (
              <ol className="flow">
                {turn.retrieved_sources.map((source) => (
                  <li key={source.source_id} className={cited.has(source.source_id) ? 'cited' : ''}>
                    <span>
                      <b className="mono">{source.source_id}</b> {source.title ?? '(제목 없음)'}
                      {cited.has(source.source_id) && <span className="sub"> · 답변 근거</span>}
                    </span>
                    <span className="num sub">{formatScore(source.score)}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="note">검색 결과가 저장되지 않았어요.</p>
            )}
            {citedOnly.length > 0 && (
              <ul className="flow">
                {citedOnly.map((source) => (
                  <li key={source.source_id} className="cited">
                    <span>
                      <b className="mono">{source.source_id}</b> {source.title ?? '(제목 없음)'}
                      <span className="sub"> · 답변 근거 (검색 후보 밖)</span>
                    </span>
                    <span className="num sub">{formatScore(source.score)}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="note">
              점수는 확률이 아니에요. 후속 질문은 두 검색을 합쳐 순서와 점수가 다를 수 있어요.
            </p>
          </section>

          <section className="sec">
            <h3>2. 판단</h3>
            <div>
              <ModeBadge status={turn.status} mode={turn.mode} errorCode={turn.error_code} />
            </div>
            {turn.status === 'failed' ? (
              <p className="note">
                시스템 오류로 답변하지 못했어요:{' '}
                {ERROR_CODE_LABEL[turn.error_code] ?? turn.error_code ?? '원인 미기록'}
              </p>
            ) : (
              <p className="note">{turn.reason ?? '판단 사유 없음'}</p>
            )}
            {turn.show_contact && <span className="badge tone-warn">고객에게 문의 카드 표시</span>}
          </section>

          <section className="sec">
            <h3>3. 답변</h3>
            <p className="msg-body">{turn.answer ?? '—'}</p>
            {turn.feedback && (
              <p className="note">
                고객 피드백 <RatingMark rating={turn.feedback.rating} />
                {turn.feedback.reason ? ` · ${FEEDBACK_REASON_LABEL[turn.feedback.reason]}` : ''}
              </p>
            )}
            {turn.inquiries.length > 0 && (
              <p className="note">
                이 답변에서 접수된 문의:{' '}
                {turn.inquiries.map((inquiry) => (
                  <button
                    key={inquiry.id}
                    type="button"
                    className="link"
                    onClick={() => navigate('inquiries', { id: inquiry.id })}
                  >
                    {inquiry.reference_no}{' '}
                  </button>
                ))}
              </p>
            )}
          </section>

          <section className="sec">
            <h3>4. 사용량</h3>
            <dl className="facts">
              <div>
                <dt>입력 / 출력 토큰</dt>
                <dd className="num">
                  {turn.prompt_tokens?.toLocaleString() ?? '—'} /{' '}
                  {turn.completion_tokens?.toLocaleString() ?? '—'}
                </dd>
              </div>
              <div>
                <dt>예상 비용</dt>
                <dd className="num">{formatUsd(turn.estimated_cost_usd, 5)}</dd>
              </div>
              <div>
                <dt>모델 · 설정</dt>
                <dd>
                  {turn.llm_model} · {turn.config_name}
                </dd>
              </div>
            </dl>
            {!chatId && (
              <button
                type="button"
                className="link"
                onClick={() => navigate('logs', { chat_id: turn.chat_id })}
              >
                이 대화 이어 보기
              </button>
            )}
          </section>
        </div>
      )}
    </State>
  );
}
