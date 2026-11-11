"""평가 스크립트 공통 유틸: 데이터셋 로딩, 구현체 로딩."""

import importlib
import json
from datetime import datetime
from pathlib import Path

import yaml

EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = EVAL_DIR / "dev_dataset.jsonl"  # 개발용. 팀 평가 세트는 --dataset으로 지정
RESULTS_DIR = EVAL_DIR / "results"


def load_dataset(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_impl(impl: str, config: str):
    """'module:factory' 문자열로 각자 구현을 불러온다. factory(config_path) -> RagSystem"""
    module_name, factory_name = impl.split(":")
    factory = getattr(importlib.import_module(module_name), factory_name)
    return factory(config)


def load_run_info(impl: str, config: str, dataset: str | Path) -> dict:
    """결과 파일에 함께 기록할 실행 정보. 임베딩 모델과 LLM 모델은 반드시 명시해야 한다."""
    from rag.config import resolve_path

    with resolve_path(config).open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    embedding_model = (cfg.get("embedding") or {}).get("model")
    llm_model = (cfg.get("generation") or {}).get("llm_model")
    if not embedding_model or not llm_model:
        raise ValueError(
            f"{config}에 embedding.model과 generation.llm_model을 반드시 적어 주세요 "
            "(결과 비교 시 어떤 모델을 썼는지 기록하기 위해)."
        )
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


def close_impl(system) -> None:
    close = getattr(system, "close", None)
    if callable(close):
        close()
