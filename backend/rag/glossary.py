"""검색 전 용어 정리: 고객 질문 속 오타·음차·줄임말을 FAQ 표준어로 바꾼다.

임베딩 검색은 "베터리", "에이에스"처럼 핵심 단어가 변형되면 정답 FAQ를 찾지 못한다.
LLM 호출을 늘리지 않으려고 규칙 기반 사전을 쓰고, 사전은 코드가 아닌 YAML 파일로 관리한다.
"""

import re
from functools import cache
from pathlib import Path

import yaml

GLOSSARY_DIR = Path(__file__).parent / "glossaries"


@cache
def load_glossary(name: str) -> tuple[tuple[re.Pattern[str], str], ...]:
    """(변형어 패턴, 표준어) 목록. 긴 변형어부터 바꿔 짧은 변형어가 먼저 끼어들지 않게 한다."""
    with (GLOSSARY_DIR / f"{name}.yaml").open(encoding="utf-8") as f:
        raw: dict[str, list[str]] = yaml.safe_load(f) or {}
    pairs = [(variant, standard) for standard, variants in raw.items() for variant in variants]
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return tuple((re.compile(re.escape(v), re.IGNORECASE), s) for v, s in pairs)


def normalize(question: str, name: str | None) -> str:
    if not name:
        return question
    for pattern, standard in load_glossary(name):
        question = pattern.sub(standard, question)
    return question
