"""RAG 파이프라인: 검색 → LLM 1회(판단 + 답변) → 결과 검사 → 숫자 검증.

LLM은 구조화 출력 한 번으로 판단 이유, 판단(answer/partial/unknown/offtopic, 선택적으로 greeting),
근거 FAQ ID, 답변을 함께 돌려준다. 판단과 답변을 따로 부르면 비용과 지연이 두 배가 되기 때문이다.
답변이 JSON 필드로 한 번에 오므로 스트리밍은 하지 않는다.
"""

import asyncio
import re
import time
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from rag.config import RagConfig, Settings, load_config
from rag.glossary import normalize
from rag.retriever import Retriever
from rag.schemas import Mode, RagResponse, Source

PROMPT_DIR = Path(__file__).parent / "prompts"
NO_CONTEXT = "(관련 FAQ 없음)"
NO_PREVIOUS = "(없음)"
CONTACT_SLOT = "{contact_email}"
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")


@cache
def load_prompts(name: str) -> dict[str, str]:
    with (PROMPT_DIR / f"{name}.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def fill_contact(prompts: dict[str, str], contact_email: str | None) -> dict[str, str]:
    """프롬프트의 {contact_email}을 설정값으로 바꾼다. 연락처는 설정 한 곳에서만 관리한다."""
    if not any(CONTACT_SLOT in text for text in prompts.values()):
        return prompts
    if not contact_email:
        raise ValueError("이 프롬프트는 generation.contact_email 설정이 필요합니다")
    return {key: text.replace(CONTACT_SLOT, contact_email) for key, text in prompts.items()}


class LlmResult(BaseModel):
    """LLM 구조화 출력. 필드 순서대로 생성되므로 판단 이유를 먼저 쓰게 한다."""

    reason: str = Field(description="질문의 핵심과 FAQ가 그 핵심을 다루는지에 대한 한 문장")
    verdict: Literal["answer", "partial", "unknown", "offtopic"] = Field(
        description="FAQ만으로 질문에 답할 수 있는지에 대한 판단"
    )
    faq_ids: list[str] = Field(description="답변 근거로 쓸 FAQ ID. unknown, offtopic이면 빈 목록")
    answer: str = Field(description="고객에게 보여 줄 답변. unknown, offtopic이면 빈 문자열")


class LlmResultWithGreeting(LlmResult):
    """인사 모드를 쓰는 프롬프트용. 기존 프롬프트의 판단 범위는 바꾸지 않으려고 따로 둔다."""

    verdict: Literal["answer", "partial", "unknown", "offtopic", "greeting"] = Field(
        description="FAQ만으로 질문에 답할 수 있는지에 대한 판단. 인사·감사·챗봇 소개 요청이면 greeting"
    )


@dataclass
class Decision:
    mode: Mode
    sources: list[Source]
    reason: str
    answer: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    retrieved: list[Source] = field(default_factory=list)


def format_context(sources: list[Source]) -> str:
    if not sources:
        return NO_CONTEXT
    return "\n\n".join(f"[{s.faq_id}] Q. {s.title}\nA. {s.excerpt}" for s in sources)


def unsupported_numbers(answer: str, sources: list[Source], question: str) -> list[str]:
    """답변에 나온 숫자 중 근거 FAQ(질문+답변)와 고객 질문 어디에도 없는 것."""
    evidence = " ".join(f"{s.title} {s.excerpt}" for s in sources) + " " + question
    known = set(NUMBER_PATTERN.findall(evidence))
    return [n for n in NUMBER_PATTERN.findall(answer) if n not in known]


def merge_alternately(first: list[Source], second: list[Source], k: int) -> list[Source]:
    """두 검색 결과를 번갈아 합친다 (중복 제거, 앞쪽 우선)."""
    merged: list[Source] = []
    seen: set[str] = set()
    pairs = [s for pair in zip(first, second, strict=False) for s in pair]
    for source in pairs + first + second:
        if source.faq_id not in seen:
            seen.add(source.faq_id)
            merged.append(source)
    return merged[:k]


RRF_K = 60  # RRF 표준 상수. 순위 차이보다 '양쪽에 모두 나왔는지'가 점수를 좌우하게 한다


def merge_rrf(first: list[Source], second: list[Source], k: int) -> list[Source]:
    """두 검색 결과를 순위 합산으로 합친다. 양쪽에 모두 나온 FAQ가 앞에 온다.

    번갈아 합치면 양쪽 모두에 나온 FAQ도 순서상 밀려 잘릴 수 있어서 둔다.
    점수가 같으면 번갈아 합친 순서(지금 질문 쪽 우선)를 따른다.
    """
    scores: dict[str, float] = {}
    for results in (first, second):
        for rank, source in enumerate(results, start=1):
            scores[source.faq_id] = scores.get(source.faq_id, 0.0) + 1 / (RRF_K + rank)
    order = merge_alternately(first, second, len(first) + len(second))
    return sorted(order, key=lambda s: -scores[s.faq_id])[:k]


class RagPipeline:
    """팀 공통 계약(RagSystem) 구현."""

    def __init__(self, config: RagConfig, settings: Settings | None = None) -> None:
        settings = settings or Settings()
        self.config = config
        gen = config.generation
        self.prompts = fill_contact(load_prompts(gen.prompt), gen.contact_email)
        self.retriever = Retriever(config, settings)

        options: dict[str, float | str] = {}
        if gen.temperature is not None:
            options["temperature"] = gen.temperature
        if gen.reasoning_effort is not None:
            options["reasoning_effort"] = gen.reasoning_effort
        llm = ChatOpenAI(model=gen.llm_model, api_key=settings.openai_api_key, **options)
        prompt = ChatPromptTemplate.from_messages(
            [("system", self.prompts["system"]), ("human", self.prompts["human"])]
        )
        # include_raw: 파싱 결과와 함께 원본 메시지(토큰 사용량)도 받는다
        self.greeting_enabled = "greeting_message" in self.prompts
        schema = LlmResultWithGreeting if self.greeting_enabled else LlmResult
        self.chain = prompt | llm.with_structured_output(
            schema, method="json_schema", strict=True, include_raw=True
        )

    # ---- 검색 ----
    async def aretrieve(self, question: str, k: int) -> list[Source]:
        return await asyncio.to_thread(self.retriever.search, question, k)

    async def _retrieve(self, question: str, previous: list[str]) -> list[Source]:
        """이전 질문이 있으면 '지금 질문'과 '이전 질문 + 지금 질문' 검색 결과를 번갈아 합친다.

        "케이스는요?" 같은 후속 질문은 붙인 검색이 맥락에 맞는 FAQ를 찾고,
        주제를 바꾼 질문은 지금 질문 단독 검색이 1순위를 지킨다.
        """
        k = self.config.retrieval.top_k
        # 용어 사전은 검색에만 쓴다. LLM에는 고객의 원래 질문을 보낸다
        glossary = self.config.retrieval.glossary
        question = normalize(question, glossary)
        previous = [normalize(p, glossary) for p in previous]
        alone = await self.aretrieve(question, k)
        if not previous:
            return alone
        joined = await self.aretrieve(" ".join([*previous, question]), k)
        if self.config.retrieval.history_merge == "rrf":
            return merge_rrf(alone, joined, k)
        return merge_alternately(alone, joined, k)

    # ---- 판단 + 답변 ----
    async def _decide(self, question: str, previous: list[str]) -> Decision:
        retrieved = await self._retrieve(question, previous)
        candidates = [s for s in retrieved if s.score >= self.config.decision.min_score]
        result = await self.chain.ainvoke(
            {
                "context": format_context(candidates),
                "question": question,
                "previous_question": "\n".join(previous) or NO_PREVIOUS,
            }
        )
        usage = (
            result["raw"].usage_metadata if isinstance(result["raw"], AIMessage) else None
        ) or {}
        decision = self._check(result["parsed"], candidates)
        decision.prompt_tokens = usage.get("input_tokens", 0)
        decision.completion_tokens = usage.get("output_tokens", 0)
        decision.retrieved = retrieved
        return decision

    @staticmethod
    def _check(parsed: LlmResult | None, candidates: list[Source]) -> Decision:
        """LLM 결과를 그대로 믿지 않고, 이상하면 안전하게 거절(unknown)한다."""
        if parsed is None:
            return Decision("unknown", [], "응답 파싱 실패")
        if parsed.verdict == "greeting":
            # 인사 답변에는 제품 사실이 없어야 한다. 숫자가 섞이면 지어낸 것으로 보고 고정 문구를 쓴다
            text = parsed.answer.strip()
            safe = text if text and not NUMBER_PATTERN.search(text) else None
            return Decision("greeting", [], parsed.reason, safe)
        if parsed.verdict in ("unknown", "offtopic"):
            # 거절 문구는 LLM 답변이 아니라 프롬프트 파일의 고정 문구를 쓴다
            return Decision(parsed.verdict, [], parsed.reason)
        by_id = {s.faq_id: s for s in candidates}
        cited = [by_id[i] for i in parsed.faq_ids if i in by_id]
        if not cited:
            # 보여 주지 않은 FAQ를 근거로 댔다면 지어낸 것으로 본다
            return Decision("unknown", [], "인용한 FAQ가 검색 결과에 없음")
        if not parsed.answer.strip():
            return Decision("unknown", [], "답변 비어 있음")
        return Decision(parsed.verdict, cited, parsed.reason, parsed.answer.strip())

    def _fixed_message(self, mode: Mode) -> str:
        key = {"offtopic": "offtopic_message", "greeting": "greeting_message"}.get(
            mode, "unknown_message"
        )
        return self.prompts[key].strip()

    # ---- 전체 ----
    async def aanswer(self, question: str, history: list[str] | None = None) -> RagResponse:
        start = time.perf_counter()
        turns = self.config.retrieval.history_turns
        previous = (history or [])[-turns:] if turns else []
        decision = await self._decide(question, previous)
        answer = decision.answer or self._fixed_message(decision.mode)

        if self.config.decision.verify_numbers and decision.mode in ("answer", "partial"):
            # 연락처의 숫자(예: 이메일 주소)는 설정에서 온 것이므로 검증에서 뺀다
            contact = self.config.generation.contact_email
            checked = answer.replace(contact, "") if contact else answer
            unsupported = unsupported_numbers(checked, decision.sources, question)
            if unsupported:
                # 근거 FAQ는 이미 골랐으니 거절하지 않고 그 원문을 보여 준다
                decision.reason = f"근거 없는 숫자 {unsupported} → FAQ 원문으로 대체"
                decision.sources = decision.sources[:1]
                answer = decision.sources[0].excerpt

        support_needed = any(
            s.faq_id in self.retriever.support_required_ids for s in decision.sources
        )
        return RagResponse(
            mode=decision.mode,
            answer=answer,
            sources=decision.sources,
            show_contact=decision.mode in ("partial", "unknown") or support_needed,
            reason=decision.reason,
            retrieved_ids=[s.faq_id for s in decision.retrieved],
            retrieved_scores=[round(s.score, 4) for s in decision.retrieved],
            latency_ms=round((time.perf_counter() - start) * 1000, 1),
            prompt_tokens=decision.prompt_tokens,
            completion_tokens=decision.completion_tokens,
        )

    def close(self) -> None:
        self.retriever.close()


def create(config_path: str) -> RagPipeline:
    """평가 스크립트용 팩토리 (--impl rag.pipeline:create)."""
    return RagPipeline(load_config(config_path))
