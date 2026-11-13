import { useState } from 'react';
import { sendInquiry } from '../api/client';

export default function InquiryForm({ sessionId, onClose }) {
  const [form, setForm] = useState({
    name: '',
    email: '',
    content: '',
    include_conversation: true,
  });
  const [status, setStatus] = useState('idle');

  const update = (key) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setStatus('sending');
    try {
      await sendInquiry({ ...form, session_id: sessionId });
      setStatus('done');
    } catch {
      setStatus('error');
    }
  };

  if (status === 'done') {
    return (
      <div className="inquiry">
        <p>문의가 접수되었어요. 담당자가 확인 후 이메일로 답변드릴게요.</p>
        <button type="button" className="pill" onClick={onClose}>
          닫기
        </button>
      </div>
    );
  }

  return (
    <form className="inquiry" onSubmit={submit}>
      <label htmlFor="inquiry-name">이름</label>
      <input id="inquiry-name" required value={form.name} onChange={update('name')} />
      <label htmlFor="inquiry-email">이메일</label>
      <input
        id="inquiry-email"
        type="email"
        required
        value={form.email}
        onChange={update('email')}
      />
      <label htmlFor="inquiry-content">문의 내용</label>
      <textarea
        id="inquiry-content"
        required
        rows={3}
        value={form.content}
        onChange={update('content')}
      />
      <label className="check">
        <input
          type="checkbox"
          checked={form.include_conversation}
          onChange={update('include_conversation')}
        />
        대화 내용 함께 보내기
      </label>
      {status === 'error' && <p className="error">접수하지 못했어요. 입력값을 확인해 주세요.</p>}
      <div className="actions">
        <button type="button" className="pill" onClick={onClose}>
          취소
        </button>
        <button type="submit" className="pill solid" disabled={status === 'sending'}>
          {status === 'sending' ? '보내는 중' : '문의 보내기'}
        </button>
      </div>
    </form>
  );
}
