import { useId, useState } from 'react';
import { ApiError, sendInquiry } from '../api/client';

const ERROR_TEXT = {
  validation_error: '입력값을 확인해 주세요.',
  rate_limited: '요청이 너무 잦아요. 잠시 후 다시 보내 주세요.',
  daily_limit_reached: '오늘은 더 접수하기 어려워요. 내일 다시 시도해 주세요.',
  service_busy: '지금은 접수가 어려워요. 잠시 후 다시 시도해 주세요.',
  db_unavailable: '일시적인 오류예요. 잠시 후 다시 시도해 주세요.',
  conflict:
    '앞서 보낸 문의와 내용이 달라 접수하지 못했어요. 한 번 더 보내 주시면 새 문의로 접수돼요.',
  unauthorized: '대화가 만료됐어요. 한 번 더 보내 주시면 대화 기록 없이 접수돼요.',
  not_found: '대화가 만료됐어요. 한 번 더 보내 주시면 대화 기록 없이 접수돼요.',
};
const DEFAULT_ERROR = '접수하지 못했어요. 잠시 후 다시 시도해 주세요.';
// 서버가 이 문의를 저장하지 않은 경우라 새 request_id로 다시 보내야 하는 오류
const NEW_REQUEST_CODES = new Set(['conflict', 'unauthorized', 'not_found']);
const EXPIRED_CODES = new Set(['unauthorized', 'not_found']);

const errorText = (error) => {
  const code = error instanceof ApiError ? error.code : null;
  if (code === 'rate_limited' && error.retryAfter) {
    return `요청이 너무 잦아요. ${error.retryAfter}초 후에 다시 보내 주세요.`;
  }
  return ERROR_TEXT[code] ?? DEFAULT_ERROR;
};

// origin: uncertain_answer_card(답변 뒤 문의 카드) | agent_request(상담사 연결) | direct_form(직접 문의)
// 문의 카드는 자기가 붙은 답변의 대화(cardChatId)와 지금 대화가 같을 때만 그 답변을 trigger로 보낸다
export default function InquiryForm({
  origin,
  cardChatId = null,
  triggerTurnId,
  chat: chatApi,
  onClose,
}) {
  const fieldId = useId();
  const [form, setForm] = useState({ name: '', email: '', content: '' });
  const [status, setStatus] = useState('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [referenceNo, setReferenceNo] = useState('');
  // 같은 문의를 다시 보내도 한 번만 접수되도록 같은 request_id를 쓴다. 서버가 저장하지 않은 오류 뒤에만 바꾼다
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());

  const isCard = origin === 'uncertain_answer_card';
  const context = chatApi.getInquiryContext();
  // 대화가 만료된 뒤 남아 있는 옛 문의 카드
  const isStaleCard = isCard && context.chat?.id !== cardChatId;
  // 서버에 저장된 질문(완료·실패)이 하나라도 있으면 이 대화가 문의에 함께 전달된다
  const isAttachingChat = context.hasSavedTurn;

  const update = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const buildPayload = async () => {
    const latest = chatApi.getInquiryContext();
    const isCurrentCard = isCard && latest.chat && latest.chat.id === cardChatId;
    // 옛 카드는 그 답변을 trigger로 쓰지 않고 직접 문의로 보낸다. 지금 대화가 있으면 그 대화를 붙인다
    const sendOrigin = isCard && !isCurrentCard ? 'direct_form' : origin;
    let chat = null;
    if (isCurrentCard) chat = latest.chat;
    else if (latest.hasSavedTurn) chat = latest.chat;
    // 상담사 연결은 대화가 필요하다. 아직 질문 전이면 대화만 만들어 보낸다(채팅 기록은 없음)
    if (sendOrigin === 'agent_request' && !chat) chat = latest.chat ?? (await chatApi.ensureChat());
    const trigger = isCurrentCard
      ? triggerTurnId
      : chat && latest.hasSavedTurn
        ? latest.lastCompletedTurnId
        : null;
    return {
      payload: {
        name: form.name.trim(),
        email: form.email.trim(),
        content: form.content.trim(),
        origin: sendOrigin,
        request_id: requestId,
        ...(chat ? { chat_id: chat.id } : {}),
        ...(chat && trigger ? { trigger_turn_id: trigger } : {}),
      },
      chat,
    };
  };

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim() || !form.content.trim()) {
      setErrorMessage('이름과 문의 내용을 적어 주세요.');
      setStatus('error');
      return;
    }
    setStatus('sending');
    let chat = null;
    try {
      const built = await buildPayload();
      chat = built.chat;
      const result = await sendInquiry(built.payload, chat?.token);
      setReferenceNo(result.reference_no);
      setStatus('done');
    } catch (error) {
      const code = error instanceof ApiError ? error.code : null;
      if (EXPIRED_CODES.has(code) && chat) chatApi.expireChat(chat.id);
      if (NEW_REQUEST_CODES.has(code)) setRequestId(crypto.randomUUID());
      setErrorMessage(errorText(error));
      setStatus('error');
    }
  };

  if (status === 'done') {
    return (
      <div className="inquiry" role="status">
        <p>
          문의가 접수되었어요{referenceNo ? ` (접수 번호 ${referenceNo})` : ''}. 담당자가 확인 후
          이메일로 연락드릴게요.
        </p>
        <button type="button" className="pill" onClick={onClose}>
          닫기
        </button>
      </div>
    );
  }

  return (
    <form className="inquiry" onSubmit={submit}>
      <label htmlFor={`${fieldId}-name`}>이름</label>
      <input
        id={`${fieldId}-name`}
        required
        maxLength={50}
        autoComplete="name"
        value={form.name}
        onChange={update('name')}
      />
      <label htmlFor={`${fieldId}-email`}>답변 받을 이메일</label>
      <input
        id={`${fieldId}-email`}
        type="email"
        required
        maxLength={254}
        autoComplete="email"
        placeholder="name@example.com"
        value={form.email}
        onChange={update('email')}
      />
      <label htmlFor={`${fieldId}-content`}>문의 내용</label>
      <textarea
        id={`${fieldId}-content`}
        required
        rows={3}
        maxLength={2000}
        placeholder="궁금한 점을 적어 주세요"
        value={form.content}
        onChange={update('content')}
      />
      {isAttachingChat && <p className="notice">이 대화 내용이 담당자에게 함께 전달돼요.</p>}
      {isStaleCard && <p className="notice">만료된 이전 대화는 함께 전달되지 않아요.</p>}
      {status === 'error' && (
        <p className="error" role="alert">
          {errorMessage}
        </p>
      )}
      <div className="actions">
        <button type="button" className="pill" onClick={onClose}>
          취소
        </button>
        <button type="submit" className="pill solid" disabled={status === 'sending'}>
          {status === 'sending' ? '보내는 중' : '문의 남기기'}
        </button>
      </div>
    </form>
  );
}
