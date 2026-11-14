import { useState } from 'react';
import { api } from '../api/client';
import { StatusBadge } from '../components/Badges';
import Conversation from '../components/Conversation';
import { PageHead } from '../components/Layout';
import Pager from '../components/Pager';
import State from '../components/State';
import { useAsync } from '../hooks/useAsync';
import { usePageClamp } from '../hooks/usePageClamp';
import {
  ORIGIN_LABEL,
  PERIODS,
  STATUS_LABEL,
  formatAgo,
  formatDateTime,
  periodDays,
  periodRange,
} from '../lib/format';

const PAGE_SIZE = 20;
const STATUS_TABS = [
  { value: 'unresolved', label: '처리 전', countKey: 'unresolved' },
  { value: 'all', label: '전체', countKey: 'total' },
  { value: 'received', label: '접수', countKey: 'received' },
  { value: 'in_progress', label: '처리 중', countKey: 'in_progress' },
  { value: 'completed', label: '완료', countKey: 'completed' },
];

export default function InquiriesPage({ params, navigate, toast, onChanged }) {
  // 화면 기본값은 "처리 전 + 전체 기간": 오래된 미처리 문의를 놓치지 않기 위해서다
  const [filters, setFilters] = useState({ status: 'unresolved', origin: '', period: 'all' });
  const [page, setPage] = useState(1);
  const selectedId = params.id ?? null;

  const range = periodRange(periodDays(filters.period));
  const list = useAsync(
    () =>
      api.listInquiries({
        status: filters.status,
        origin: filters.origin,
        ...range,
        page,
        size: PAGE_SIZE,
      }),
    JSON.stringify([filters, page]),
  );
  const counts = useAsync(
    () => api.inquiryCounts({ origin: filters.origin, ...range }),
    JSON.stringify([filters.origin, filters.period]),
  );

  const refresh = () => {
    list.reload();
    counts.reload();
    onChanged();
  };

  const setFilter = (key) => (value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const select = (id) => navigate('inquiries', { id });
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
        title="문의 관리"
        description="챗봇에서 들어온 문의를 확인하고 처리 상태를 기록해요. 답장은 회사에서 직접 해요."
      />
      <div className={`inq ${selectedId ? 'has-selection' : ''}`}>
        <section className="card inq-list" aria-label="문의 목록">
          <div className="card-head">
            <h2>문의 목록</h2>
            <span className="sub num">{list.data ? `${list.data.total_count}건` : ''}</span>
          </div>
          <div className="filters">
            <div className="seg" role="group" aria-label="처리 상태">
              {STATUS_TABS.map((tab) => (
                <button
                  key={tab.value}
                  type="button"
                  aria-pressed={filters.status === tab.value}
                  onClick={() => setFilter('status')(tab.value)}
                >
                  {tab.label}
                  {counts.data && <span className="num"> {counts.data[tab.countKey]}</span>}
                </button>
              ))}
            </div>
            <select
              aria-label="유입 경로"
              value={filters.origin}
              onChange={(event) => setFilter('origin')(event.target.value)}
            >
              <option value="">유입 경로 전체</option>
              {Object.entries(ORIGIN_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <select
              aria-label="기간"
              value={filters.period}
              onChange={(event) => setFilter('period')(event.target.value)}
            >
              {PERIODS.map((period) => (
                <option key={period.value} value={period.value}>
                  {period.label}
                </option>
              ))}
            </select>
          </div>
          <State
            isLoading={list.isLoading}
            error={list.error}
            isEmpty={!items.length}
            emptyText="조건에 맞는 문의가 없어요."
            onRetry={list.reload}
          >
            <div>
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="inq-item"
                  aria-current={item.id === selectedId}
                  onClick={() => select(item.id)}
                >
                  <span className="row1">
                    <span className="who">
                      {item.is_unread && (
                        <span className="unread-dot" title="확인 안 함">
                          <span className="sr-only">확인 안 함</span>
                        </span>
                      )}
                      {item.name}
                    </span>
                    <StatusBadge status={item.status} />
                  </span>
                  <span className="preview">{item.content_preview}</span>
                  <span className="when">
                    {formatDateTime(item.created_at)} · {ORIGIN_LABEL[item.origin]}
                    {item.has_conversation ? ' · 대화 있음' : ''}
                  </span>
                </button>
              ))}
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
        <section className="card detail-panel" aria-label="문의 상세">
          {selectedId ? (
            <InquiryDetail
              key={selectedId}
              id={selectedId}
              navigate={navigate}
              toast={toast}
              onChanged={refresh}
            />
          ) : (
            <div className="empty">왼쪽에서 문의를 고르면 내용과 챗봇 대화가 보여요.</div>
          )}
        </section>
      </div>
    </>
  );
}

function InquiryDetail({ id, navigate, toast, onChanged }) {
  const detail = useAsync(async () => {
    const loaded = await api.getInquiry(id);
    if (!loaded.is_unread) return loaded;
    // 상세를 연 순간 읽음 처리한다. 목록을 보는 것만으로는 읽음이 되지 않는다
    try {
      const viewed = await api.updateInquiry(id, { viewed: true });
      onChanged();
      return viewed;
    } catch {
      // 읽음 표시만 실패한 것이므로 내용은 그대로 보여 주고, 다음에 열 때 다시 시도한다
      toast('읽음 표시를 저장하지 못했어요.');
      return loaded;
    }
  }, id);
  const [isSaving, setIsSaving] = useState(false);
  const inquiry = detail.data;

  const save = async (patch, message) => {
    setIsSaving(true);
    try {
      const updated = await api.updateInquiry(id, patch);
      detail.setData(updated);
      onChanged();
      toast(message);
    } catch (error) {
      toast(error.message || '저장하지 못했어요.');
    } finally {
      setIsSaving(false);
    }
  };

  const copyEmail = async () => {
    try {
      await navigator.clipboard.writeText(inquiry.email);
      toast('이메일 주소를 복사했어요');
    } catch {
      toast('복사하지 못했어요. 주소를 직접 선택해 주세요.');
    }
  };

  return (
    <State
      isLoading={detail.isLoading}
      error={detail.error}
      isEmpty={!inquiry}
      onRetry={detail.reload}
    >
      {inquiry && (
        <div>
          <div className="card-head">
            <h2>
              <button type="button" className="link back" onClick={() => navigate('inquiries')}>
                ← 목록
              </button>
              {inquiry.name}님의 문의 <span className="sub mono">{inquiry.reference_no}</span>
            </h2>
            <StatusBadge status={inquiry.status} />
          </div>
          <div className="detail-body">
            <dl className="facts">
              <div>
                <dt>이메일</dt>
                <dd>
                  <span className="mono">{inquiry.email}</span>
                  <button type="button" className="btn small" onClick={copyEmail}>
                    복사
                  </button>
                </dd>
              </div>
              <div>
                <dt>접수 시각</dt>
                <dd>
                  <span className="num">{formatDateTime(inquiry.created_at)}</span>
                  <span className="sub">{formatAgo(inquiry.created_at)}</span>
                </dd>
              </div>
              <div>
                <dt>유입 경로</dt>
                <dd>{ORIGIN_LABEL[inquiry.origin]}</dd>
              </div>
            </dl>

            <section className="sec">
              <h3>문의 내용</h3>
              <p className="msg-body">{inquiry.content}</p>
            </section>

            <section className="sec">
              <div className="row-between">
                <h3>문의 직전 챗봇 대화</h3>
                {inquiry.chat_id && (
                  <button
                    type="button"
                    className="link"
                    onClick={() => navigate('logs', { chat_id: inquiry.chat_id })}
                  >
                    이 대화 전체를 질문 로그에서 보기
                  </button>
                )}
              </div>
              {inquiry.conversation.length ? (
                <Conversation turns={inquiry.conversation} />
              ) : (
                <p className="note">
                  {inquiry.chat_id
                    ? '대화를 시작하기 전에 접수한 문의라 채팅 기록이 없어요.'
                    : '대화 없이 직접 접수한 문의예요.'}
                </p>
              )}
            </section>

            <section className="sec">
              <h3>처리 상태</h3>
              <div className="seg" role="group" aria-label="처리 상태 변경">
                {Object.entries(STATUS_LABEL).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={inquiry.status === value}
                    disabled={isSaving}
                    onClick={() =>
                      inquiry.status !== value &&
                      save(
                        { status: value },
                        `${inquiry.reference_no} 상태를 '${label}'(으)로 바꿨어요`,
                      )
                    }
                  >
                    {label}
                  </button>
                ))}
              </div>
              {inquiry.completed_at && (
                <p className="note">완료 시각 {formatDateTime(inquiry.completed_at)}</p>
              )}
            </section>

            <MemoEditor
              key={inquiry.id}
              savedNote={inquiry.internal_note}
              isSaving={isSaving}
              onSave={(note) => save({ internal_note: note }, '메모를 저장했어요')}
            />
          </div>
        </div>
      )}
    </State>
  );
}

// 문의마다 key로 새로 만들어 저장된 메모로 시작한다
function MemoEditor({ savedNote, isSaving, onSave }) {
  const [note, setNote] = useState(savedNote);
  return (
    <section className="sec">
      <h3>
        <label htmlFor="memo">내부 메모</label>
      </h3>
      <textarea
        id="memo"
        maxLength={2000}
        placeholder="처리 내용이나 전달 사항을 적어 두세요. 고객에게는 보이지 않아요."
        value={note}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="row-between">
        <span className="note">관리자만 보는 메모예요. {note.length}/2000</span>
        <button
          type="button"
          className="btn primary"
          disabled={isSaving || note === savedNote}
          onClick={() => onSave(note)}
        >
          메모 저장
        </button>
      </div>
    </section>
  );
}
