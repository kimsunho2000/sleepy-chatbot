import { Fragment, useState } from 'react';
import { api } from '../api/client';
import { ModeBadge, RatingMark } from '../components/Badges';
import { PageHead } from '../components/Layout';
import Pager from '../components/Pager';
import State from '../components/State';
import { useAsync } from '../hooks/useAsync';
import { usePageClamp } from '../hooks/usePageClamp';
import { PERIODS, formatAgo, formatDateTime, periodDays, periodRange } from '../lib/format';

const PAGE_SIZE = 20;
// 이 API는 기간을 생략하면 전체가 아니라 최근 30일이라 '전체 기간' 옵션을 두지 않는다
const GROUP_PERIODS = PERIODS.filter((option) => option.value !== 'all');

function kinds(group) {
  return [
    group.unknown_count && `답변 불가 ${group.unknown_count}`,
    group.partial_count && `부분 답변 ${group.partial_count}`,
    group.downvote_count && `👎 ${group.downvote_count}`,
  ]
    .filter(Boolean)
    .join(' · ');
}

// 의미 묶음이 아니라 "검색 1순위 FAQ가 같은 질문"이라 FAQ 제목 근처로 표시한다
function groupTitle(group) {
  return group.group_key === 'none'
    ? '검색 결과가 없는 질문'
    : `〈${group.source_title ?? group.group_key}〉 근처 질문`;
}

export default function UnansweredPage({ navigate }) {
  const [period, setPeriod] = useState('30');
  const [page, setPage] = useState(1);
  const [openKey, setOpenKey] = useState(null);
  const range = periodRange(periodDays(period));
  const list = useAsync(
    () => api.listUnansweredGroups({ ...range, page, size: PAGE_SIZE }),
    JSON.stringify([period, page]),
  );
  usePageClamp({
    page,
    size: PAGE_SIZE,
    total: list.data?.total_count,
    isLoading: list.isLoading,
    setPage,
  });
  const items = list.data?.items ?? [];
  const max = Math.max(1, ...items.map((group) => group.occurrence_count));

  return (
    <>
      <PageHead
        title="답 못 한 질문"
        description="답변 불가·부분 답변이었거나 👎를 받은 질문을, 검색 1순위 FAQ가 같은 것끼리 묶었어요. 자주 나온 묶음부터 FAQ 보강을 검토하세요."
      />
      <section className="card">
        <div className="card-head">
          <h2>질문 묶음</h2>
          <span className="sub">횟수 많은 순</span>
        </div>
        <div className="filters">
          <select
            aria-label="기간"
            value={period}
            onChange={(event) => {
              setPeriod(event.target.value);
              setPage(1);
            }}
          >
            {GROUP_PERIODS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <State
          isLoading={list.isLoading}
          error={list.error}
          isEmpty={!items.length}
          emptyText="이 기간에 답하지 못한 질문이 없어요."
          onRetry={list.reload}
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>질문 묶음</th>
                  <th>횟수</th>
                  <th>유형</th>
                  <th>최근</th>
                  <th>들어온 문의</th>
                </tr>
              </thead>
              <tbody>
                {items.map((group) => {
                  const isOpen = openKey === group.group_key;
                  const toggle = () => setOpenKey(isOpen ? null : group.group_key);
                  return (
                    <Fragment key={group.group_key}>
                      <tr
                        className={`click ${isOpen ? 'open' : ''}`}
                        tabIndex={0}
                        aria-expanded={isOpen}
                        onClick={toggle}
                        onKeyDown={(event) => {
                          // 안쪽 문의 번호 버튼에서 누른 키는 그 버튼이 처리하게 둔다
                          if (event.target !== event.currentTarget) return;
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            toggle();
                          }
                        }}
                      >
                        <td className="q">
                          {groupTitle(group)}
                          <div className="sub">최근 질문: “{group.representative_question}”</div>
                        </td>
                        <td>
                          <div className="bar-cell">
                            <span className="num">{group.occurrence_count}</span>
                            <svg width="60" height="6" aria-hidden="true">
                              <rect
                                className="mini-bar"
                                width={Math.round((group.occurrence_count / max) * 60)}
                                height="6"
                                rx="3"
                              />
                            </svg>
                          </div>
                        </td>
                        <td className="sub">{kinds(group)}</td>
                        <td className="sub num">{formatAgo(group.last_seen_at)}</td>
                        <td>
                          {group.inquiries.length ? (
                            group.inquiries.map((inquiry) => (
                              <button
                                key={inquiry.id}
                                type="button"
                                className="link"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  navigate('inquiries', { id: inquiry.id });
                                }}
                              >
                                {inquiry.reference_no}{' '}
                              </button>
                            ))
                          ) : (
                            <span className="sub">없음</span>
                          )}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr>
                          <td colSpan={5} className="detail-cell">
                            <GroupDetail
                              // 기간이 바뀌면 상세의 페이지도 처음부터 다시 본다
                              key={`${range.from ?? ''}-${range.to ?? ''}`}
                              groupKey={group.group_key}
                              range={range}
                              navigate={navigate}
                            />
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
        묶는 기준은 초기안이에요. 근거가 없는 질문일수록 1순위 FAQ가 엉뚱할 수 있어요.
      </p>
    </>
  );
}

function GroupDetail({ groupKey, range, navigate }) {
  const [page, setPage] = useState(1);
  const detail = useAsync(
    () => api.getUnansweredGroup(groupKey, { ...range, page, size: 10 }),
    // 목록 기간이 바뀌면 펼쳐 둔 상세도 같은 기간으로 다시 불러온다
    JSON.stringify([groupKey, page, range.from, range.to]),
  );
  usePageClamp({
    page,
    size: 10,
    total: detail.data?.turns.total_count,
    isLoading: detail.isLoading,
    setPage,
  });
  const data = detail.data;
  return (
    <State
      isLoading={detail.isLoading}
      error={detail.error}
      isEmpty={!data}
      onRetry={detail.reload}
    >
      {data && (
        <div className="log-detail">
          <section className="sec">
            <h3>비슷한 질문</h3>
            <ol className="flow">
              {data.variants.map((variant) => (
                <li key={variant.question}>
                  <span>“{variant.question}”</span>
                  <span className="num sub">{variant.count}회</span>
                </li>
              ))}
            </ol>
          </section>
          <section className="sec">
            <h3>질문 기록</h3>
            <ol className="flow">
              {data.turns.items.map((turn) => (
                <li key={turn.turn_id}>
                  <span>
                    <span className="sub num">{formatDateTime(turn.created_at)}</span>{' '}
                    {turn.question} <ModeBadge status={turn.status} mode={turn.mode} />{' '}
                    <RatingMark rating={turn.rating} />
                  </span>
                  <button
                    type="button"
                    className="link"
                    onClick={() => navigate('logs', { chat_id: turn.chat_id })}
                  >
                    대화 보기
                  </button>
                </li>
              ))}
            </ol>
            <Pager
              page={page}
              size={10}
              total={data.turns.total_count}
              isLoading={detail.isLoading}
              onChange={setPage}
            />
          </section>
        </div>
      )}
    </State>
  );
}
