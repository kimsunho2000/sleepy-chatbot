"""FAQ JSON 로딩. 항목 개수나 특정 문구에 의존하지 않는다."""

import json
from pathlib import Path

from rag.config import resolve_path
from rag.schemas import FaqItem


def load_faq(path: str | Path) -> list[FaqItem]:
    with resolve_path(path).open(encoding="utf-8") as f:
        items = [FaqItem.model_validate(raw) for raw in json.load(f)]

    ids = [item.faq_id for item in items]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"중복된 faq_id: {sorted(duplicates)}")
    return items


def load_confirmed_faq(path: str | Path) -> list[FaqItem]:
    """답변이 확정된 항목만 반환한다. 인덱싱 대상."""
    return [item for item in load_faq(path) if item.status == "confirmed" and item.answer.strip()]
