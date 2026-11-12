"""평가 스크립트 공통 유틸: 데이터셋·구현체 로딩, 실행 정보 기록."""

import importlib
import json
from datetime import datetime
from pathlib import Path

import yaml

from rag.config import resolve_path
from rag.schemas import RagSystem

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = EVAL_DIR / "dev_dataset.jsonl"  # 개발용. 팀 평가 세트는 --dataset으로 지정
RESULTS_DIR = EVAL_DIR / "results"


def load_dataset(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def previous_questions(item: dict) -> list[str]:
    """평가 문항의 history에서 고객 질문만 꺼낸다 (프론트엔드가 보내는 것과 같은 형태)."""
    return [turn["content"] for turn in item.get("history", []) if turn["role"] == "user"]


def load_impl(impl: str, config: str) -> RagSystem:
    """'module:factory' 문자열로 구현을 불러온다. 팀원마다 다른 구현을 같은 스크립트로 평가하기 위해서다."""
    module_name, factory_name = impl.split(":")
    factory = getattr(importlib.import_module(module_name), factory_name)
    return factory(config)


def close_impl(system: RagSystem) -> None:
    close = getattr(system, "close", None)
    if callable(close):
        close()


def load_run_info(impl: str, config: str, dataset: str | Path) -> dict:
    """결과 파일에 함께 기록할 실행 정보. 어떤 모델로 낸 결과인지 남기려고 모델명을 필수로 받는다."""
    with resolve_path(config).open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    embedding_model = (cfg.get("embedding") or {}).get("model")
    llm_model = (cfg.get("generation") or {}).get("llm_model")
    if not embedding_model or not llm_model:
        raise ValueError(f"{config}에 embedding.model과 generation.llm_model을 적어 주세요")
    return {
        "run": cfg.get("name", Path(config).stem),
        "owner": cfg.get("owner", ""),
        "impl": impl,
        "config_path": str(config),
        "dataset": str(dataset),
        "embedding_model": embedding_model,
        "llm_model": llm_model,
        "config": cfg,
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
