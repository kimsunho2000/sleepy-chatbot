"""관리자 문의 관리 API 스키마 (목록, 건수, 상세, 수정)."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.inquiry import InquiryOrigin, InquiryStatus

# 목록 필터. unresolved는 received + in_progress ("처리 전")
InquiryStatusFilter = Literal["unresolved", "all", "received", "in_progress", "completed"]
TurnStatus = Literal["completed", "failed"]
TurnMode = Literal["answer", "partial", "unknown", "offtopic", "greeting"]

INTERNAL_NOTE_MAX_LENGTH = 2000


class InquirySummary(BaseModel):
    """목록의 한 줄. 이메일, 메모, 채팅 기록은 상세에만 있다."""

    id: uuid.UUID
    reference_no: str
    name: str
    content_preview: str
    origin: InquiryOrigin
    status: InquiryStatus
    # 아직 관리자가 읽음 처리하지 않았다 (처리 상태와 별개)
    is_unread: bool
    # conversation이 1개 이상인 문의. 저장된 turn이 없는 대화의 상담사 연결은 false
    has_conversation: bool
    created_at: datetime


class InquiryListResponse(BaseModel):
    items: list[InquirySummary]
    page: int
    size: int
    total_count: int


class InquiryCounts(BaseModel):
    received: int
    in_progress: int
    completed: int
    # 처리 전 = received + in_progress
    unresolved: int
    # 읽음 처리 전인 문의 수. 상태와 무관하다
    unread: int
    total: int


class SourceRef(BaseModel):
    rank: int
    source_id: str
    # 저장 당시 제목. 찾지 못했으면 null
    title: str | None
    score: float | None


class ConversationTurn(BaseModel):
    turn_id: uuid.UUID
    question: str
    # 같은 값을 가진 turn이 여럿이면 같은 자리에서 갈라진 답변 시도다
    parent_turn_id: uuid.UUID | None
    status: TurnStatus
    mode: TurnMode | None
    answer: str | None
    # 답변에 실제로 쓴 근거. 답변 불가·범위 밖 turn은 비어 있다
    cited_sources: list[SourceRef]
    # 검색 후보 상위 3개
    retrieved_sources: list[SourceRef] = Field(max_length=3)
    is_trigger: bool
    created_at: datetime


class InquiryDetail(InquirySummary):
    email: EmailStr
    content: str
    internal_note: str
    first_viewed_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    chat_id: uuid.UUID | None
    trigger_turn_id: uuid.UUID | None
    conversation: list[ConversationTurn]


class InquiryUpdate(BaseModel):
    """보내지 않은 필드는 그대로 둔다. 하나 이상 보내야 한다."""

    # minProperties는 명세(Swagger)에 "최소 1개 필드"가 드러나게 하려는 문서용 값이다.
    # 실제 검사는 아래 need_one_field가 한다
    model_config = ConfigDict(extra="forbid", json_schema_extra={"minProperties": 1})

    # true만 받는다. 읽음을 되돌리는 기능은 없다
    viewed: Literal[True] | None = None
    status: InquiryStatus | None = None
    # 빈 문자열이면 메모를 지운다. null은 "보내지 않음"과 같아서 받지 않는다
    internal_note: str | None = Field(default=None, max_length=INTERNAL_NOTE_MAX_LENGTH)

    @model_validator(mode="after")
    def need_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("변경할 필드를 하나 이상 보내 주세요.")
        # 명시적 null은 "지우기"로 오해하기 쉬워 거절한다
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name}에는 null을 보낼 수 없어요.")
        return self
