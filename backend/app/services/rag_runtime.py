"""서버 시작 때 한 번 만드는 RAG와, turn을 저장할 때 필요한 설정 정보."""

from collections.abc import Callable
from dataclasses import dataclass, field

import openai

from rag.config import load_config
from rag.data_loader import load_confirmed_items
from rag.errors import ParseError, RetrievalError
from rag.schemas import RagSystem


@dataclass
class RagRuntime:
    system: RagSystem
    # 검색 후보 ID → 제목. TURN_SOURCE에 저장 당시 제목을 남긴다
    titles: dict[str, str]
    # 부모를 따라 올라가며 꺼낼 이전 질문 수 (RAG 설정 retrieval.history_turns)
    history_turns: int
    config_name: str
    llm_model: str
    close: Callable[[], None] = field(default=lambda: None)


def load_rag_runtime(config_path: str) -> RagRuntime:
    # 모듈을 불러올 때 Qdrant·OpenAI 클라이언트가 만들어지지 않도록 여기서 가져온다
    from rag.pipeline import RagPipeline

    config = load_config(config_path)
    pipeline = RagPipeline(config)
    items = load_confirmed_items(config.data_paths)
    return RagRuntime(
        system=pipeline,
        titles={item.faq_id: item.question for item in items},
        history_turns=config.retrieval.history_turns,
        config_name=config.name,
        llm_model=config.generation.llm_model,
        close=pipeline.close,
    )


def classify_rag_error(exc: BaseException) -> str:
    """RAG 실패를 관리자용 error_code로 바꾼다. 고객에게는 ai_unavailable로 묶어 보여 준다."""
    if isinstance(exc, RetrievalError):
        # 크레딧 소진·속도 제한은 대개 LLM보다 먼저 부르는 임베딩에서 난다. 원인으로 분류해야 드러난다
        cause = exc.__cause__
        if isinstance(cause, openai.RateLimitError | openai.APITimeoutError):
            return classify_rag_error(cause)
        return "retrieval_error"
    if isinstance(exc, ParseError):
        return "llm_parse_error"
    if isinstance(exc, openai.RateLimitError):
        # 크레딧 소진도 429로 오지만 기다려도 풀리지 않으니 따로 센다
        return "llm_quota" if exc.code == "insufficient_quota" else "llm_rate_limit"
    if isinstance(exc, openai.APITimeoutError):
        return "llm_timeout"
    return "llm_error"
