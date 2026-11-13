"""문의 접수 API 스키마."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

InquiryOrigin = Literal["uncertain_answer_card", "agent_request", "direct_form"]
InquiryStatus = Literal["received", "in_progress", "completed"]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Email = Annotated[EmailStr, StringConstraints(max_length=254)]


class InquiryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    email: Email
    content: Content
    origin: InquiryOrigin
    # 대화가 시작된 상태면 필수. 화면에 보이는 마지막 완료 turn
    chat_id: uuid.UUID | None = None
    trigger_turn_id: uuid.UUID | None = None
    request_id: uuid.UUID


class InquiryResponse(BaseModel):
    inquiry_id: uuid.UUID
    reference_no: str
    status: InquiryStatus
    created_at: datetime
