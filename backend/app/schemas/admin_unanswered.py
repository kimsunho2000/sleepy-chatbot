"""관리자 미답변 조회 응답. 문의 개인정보와 인증정보는 포함하지 않는다."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.admin_common import LinkedInquiry, Page
from app.schemas.chat import Mode, Rating


class UnansweredGroup(BaseModel):
    group_key: str
    source_title: str | None
    representative_question: str
    occurrence_count: int
    unknown_count: int
    partial_count: int
    downvote_count: int
    last_seen_at: datetime
    inquiries: list[LinkedInquiry]


class QuestionVariant(BaseModel):
    question: str
    count: int


class UnansweredTurn(BaseModel):
    turn_id: uuid.UUID
    chat_id: uuid.UUID
    question: str
    status: Literal["completed"]
    mode: Mode
    latency_ms: float | None
    rating: Rating | None
    created_at: datetime
    inquiries: list[LinkedInquiry]


class GroupDetail(BaseModel):
    group: UnansweredGroup
    variants: list[QuestionVariant]
    turns: Page[UnansweredTurn]
