"""관리자 API가 함께 쓰는 형식. 질문 로그, 문의 관리, 답 못 한 질문이 같은 정의를 쓴다."""

import uuid
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T")

TurnStatus = Literal["completed", "failed"]


class Page(BaseModel, Generic[T]):
    """페이지 번호 목록 응답. 기본 정렬은 최신순이다."""

    items: list[T]
    page: int
    size: int
    total_count: int


class SourceItem(BaseModel):
    """검색 후보 또는 답변 근거 1건. score는 검색 점수이고 확률이 아니다."""

    rank: int
    source_id: str
    # 저장 당시 제목. 찾지 못했으면 null
    title: str | None
    score: float | None


class LinkedInquiry(BaseModel):
    """turn에서 접수된 문의. 화면에는 INQ-1024 같은 번호를 표시한다."""

    id: uuid.UUID
    reference_no: str
