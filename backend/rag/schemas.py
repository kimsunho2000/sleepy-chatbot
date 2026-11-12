"""RAG 모듈의 데이터 구조와 팀 공통 계약(RagSystem)."""

from typing import Literal, Protocol

from pydantic import BaseModel, Field

# greeting: 인사·감사·챗봇 소개 요청. 프롬프트에 greeting_message가 있을 때만 나온다
Mode = Literal["answer", "partial", "unknown", "offtopic", "greeting"]


class FaqItem(BaseModel):
    faq_id: str
    category: str
    question: str
    answer: str = ""
    source: str
    status: Literal["confirmed", "pending", "draft"]
    company_provided: bool = False
    support_required: bool = False


class Source(BaseModel):
    """답변 근거로 보여 줄 FAQ. 프론트의 '참고한 자료' 칩과 같은 구조."""

    faq_id: str
    title: str
    category: str
    score: float
    excerpt: str


class RagResponse(BaseModel):
    mode: Mode
    answer: str
    sources: list[Source] = Field(default_factory=list)
    # 담당자 문의 카드를 보여 줄지 (불확실한 답변, 고객센터 연결이 필요한 FAQ)
    show_contact: bool = False
    # 판단 근거 (디버깅·평가용, 고객에게 보여 주지 않는다)
    reason: str = ""
    # 판단 전 검색 후보. 평가에서 검색 실패와 판단 실패를 구분하는 데 쓴다 (고객에게 보여 주지 않는다)
    retrieved_ids: list[str] = Field(default_factory=list)
    retrieved_scores: list[float] = Field(default_factory=list)
    latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class RagSystem(Protocol):
    """팀원 구현이 모두 지켜야 하는 공통 계약. 평가 스크립트는 이것만 호출한다."""

    async def aretrieve(self, question: str, k: int) -> list[Source]: ...

    # history: 같은 대화에서 고객이 앞서 한 질문들 (오래된 것부터).
    # 프론트엔드가 보내고 서버는 저장하지 않는다. 선택 인자라 쓰지 않는 구현은 무시해도 된다.
    async def aanswer(self, question: str, history: list[str] | None = None) -> RagResponse: ...
