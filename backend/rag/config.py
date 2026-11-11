"""RAG 설정(YAML)과 환경변수 로딩."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: SecretStr


class EmbeddingConfig(BaseModel):
    model: str = "text-embedding-3-large"


class RetrievalConfig(BaseModel):
    top_k: int = 4
    # top_k 자리 중 키워드 검색(2글자 BM25) 1등에게 내줄 자리 수. 0이면 임베딩 검색만 쓴다.
    # 질문에 다른 말이 많으면 임베딩 검색이 핵심 단어("음악")를 놓칠 때가 있어서 둔다.
    keyword_slots: int = Field(default=0, ge=0)
    # 고객의 이전 질문을 몇 개까지 검색과 판단에 쓸지. 0이면 이전 질문을 무시한다.
    # "케이스는요?" 같은 후속 질문을 이해하기 위해 쓴다.
    history_turns: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_slots(self) -> "RetrievalConfig":
        if self.keyword_slots >= self.top_k:
            raise ValueError(
                "keyword_slots는 top_k보다 작아야 합니다 (임베딩 자리가 최소 1개 필요)"
            )
        return self


class DecisionConfig(BaseModel):
    # 이 점수(코사인 유사도) 미만인 검색 결과는 LLM에 넘기지 않는다
    min_score: float = 0.15
    # 답변 속 숫자가 근거 FAQ와 질문에 없으면 LLM 답변 대신 근거 FAQ 원문을 보여 준다.
    # LLM이 시간·횟수·기간을 지어내는 것을 막기 위한 장치
    verify_numbers: bool = True


class GenerationConfig(BaseModel):
    llm_model: str
    # 비우면 모델 기본값. 추론 모델은 reasoning_effort가 "none"일 때만 temperature를 받는다
    temperature: float | None = None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None
    # backend/rag/prompts/{prompt}.yaml
    prompt: str = "default"
    # 프롬프트의 {contact_email} 자리에 들어갈 고객상담 이메일
    contact_email: str | None = None


class RagConfig(BaseModel):
    model_config = {"extra": "forbid"}  # 설정 파일 오타를 조용히 무시하지 않도록

    name: str
    owner: str = ""
    description: str = ""
    data_path: str = "data/faq.json"
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    generation: GenerationConfig

    @property
    def qdrant_path(self) -> Path:
        return REPO_ROOT / ".qdrant" / self.name

    @property
    def collection_name(self) -> str:
        return f"sleeby_{self.name}"


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def load_config(path: str | Path) -> RagConfig:
    with resolve_path(path).open(encoding="utf-8") as f:
        return RagConfig.model_validate(yaml.safe_load(f))
