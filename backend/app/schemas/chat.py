"""고객 챗봇 API 스키마. 출처·판단 사유·토큰은 고객 응답에 넣지 않는다."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Mode = Literal["answer", "partial", "unknown", "offtopic", "greeting"]
Rating = Literal["up", "down"]
FeedbackReason = Literal["wrong", "insufficient", "irrelevant"]


class ChatResponse(BaseModel):
    chat_id: uuid.UUID
    # 한 번 발급하는 대화 소유권 토큰. 로그에 남기지 않는다
    chat_token: str
    created_at: datetime


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Question
    parent_turn_id: uuid.UUID | None = None


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: Rating
    reason: FeedbackReason | None = None

    @model_validator(mode="after")
    def reason_only_for_down(self) -> "FeedbackRequest":
        if self.rating == "up" and self.reason is not None:
            raise ValueError("reason은 rating=down일 때만 보낼 수 있어요")
        return self


class FeedbackResponse(BaseModel):
    rating: Rating
    reason: FeedbackReason | None
    updated_at: datetime


class TurnResponse(BaseModel):
    turn_id: uuid.UUID
    chat_id: uuid.UUID
    parent_turn_id: uuid.UUID | None
    question: str
    mode: Mode
    answer: str
    show_contact: bool
    feedback: FeedbackResponse | None
    created_at: datetime
