"""관리자 질문 로그·대시보드 API 스키마.

출처, 판단 사유, 토큰, 예상 비용은 관리자 API에서만 내보낸다.
"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.admin_common import LinkedInquiry, SourceItem, TurnStatus
from app.schemas.chat import FeedbackResponse, Mode, Rating

RatingFilter = Literal["up", "down", "none"]
TurnErrorCode = Literal[
    "llm_rate_limit",
    "llm_quota",
    "llm_timeout",
    "llm_parse_error",
    "llm_error",
    "retrieval_error",
]


class TurnLogItem(BaseModel):
    turn_id: uuid.UUID
    chat_id: uuid.UUID
    question: str
    status: TurnStatus
    mode: Mode | None
    latency_ms: float | None
    rating: Rating | None
    created_at: datetime


class TurnLogDetail(BaseModel):
    turn_id: uuid.UUID
    chat_id: uuid.UUID
    parent_turn_id: uuid.UUID | None
    question: str
    status: TurnStatus
    # 실패 turn은 mode와 answer가 없고 error_code만 있다
    mode: Mode | None
    answer: str | None
    show_contact: bool
    reason: str | None
    error_code: TurnErrorCode | None
    retrieved_sources: list[SourceItem]
    cited_sources: list[SourceItem]
    latency_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    # 토큰 × 설정 단가로 계산한 예상치. 단가나 토큰이 없으면 null
    estimated_cost_usd: float | None
    llm_model: str
    config_name: str
    feedback: FeedbackResponse | None
    inquiries: list[LinkedInquiry]
    created_at: datetime
    finished_at: datetime


class ModeCounts(BaseModel):
    answer: int = 0
    partial: int = 0
    unknown: int = 0
    offtopic: int = 0
    greeting: int = 0


class FailedByReason(BaseModel):
    llm_rate_limit: int = 0
    llm_quota: int = 0
    llm_timeout: int = 0
    llm_parse_error: int = 0
    llm_error: int = 0
    retrieval_error: int = 0


class DailyCount(BaseModel):
    # 한국 날짜 (Asia/Seoul)
    date: date
    count: int


class TopSource(BaseModel):
    source_id: str
    title: str | None
    count: int


class DashboardResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # 실제로 집계한 기간. from 포함, to 미포함 (UTC)
    period_from: datetime = Field(alias="from")
    period_to: datetime = Field(alias="to")
    question_count: int
    mode_counts: ModeCounts
    failed_count: int
    failed_by_reason: FailedByReason
    average_latency_ms: float | None
    # 비율은 0~1. 분모가 0이면 null
    uncertain_ratio: float | None
    feedback_count: int
    positive_feedback_ratio: float | None
    estimated_cost_usd: float | None
    average_cost_usd: float | None
    # 기간과 무관한 전체 문의 수
    unresolved_inquiry_count: int
    unread_inquiry_count: int
    daily_questions: list[DailyCount]
    top_sources: list[TopSource]
