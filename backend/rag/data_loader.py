"""FAQ JSON 로딩. 항목 개수나 특정 문구에 의존하지 않는다."""

import json
from pathlib import Path

from rag.config import resolve_path
from rag.schemas import FaqItem

# 관리자 "답 못 한 질문"에서 검색 결과 없음 묶음의 키로 쓴다.
# 이 검사 전에 저장된 로그에도 source_id='none'이 없다는 전제다 (지금까지의 FAQ ID는 Q·P로 시작)
RESERVED_IDS = frozenset({"none"})


def load_faq(path: str | Path) -> list[FaqItem]:
    with resolve_path(path).open(encoding="utf-8") as f:
        items = [FaqItem.model_validate(raw) for raw in json.load(f)]

    ids = [item.faq_id for item in items]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"중복된 faq_id: {sorted(duplicates)}")
    reserved = RESERVED_IDS.intersection(ids)
    if reserved:
        raise ValueError(f"예약된 faq_id는 쓸 수 없어요: {sorted(reserved)}")
    return items


def load_confirmed_faq(path: str | Path) -> list[FaqItem]:
    """답변이 확정된 항목만 반환한다. 인덱싱 대상."""
    return [item for item in load_faq(path) if item.status == "confirmed" and item.answer.strip()]


def load_confirmed_items(paths: list[str]) -> list[FaqItem]:
    """여러 데이터 파일의 확정 항목을 합친다. ID는 파일을 통틀어 겹치면 안 된다."""
    items = [item for path in paths for item in load_confirmed_faq(path)]
    ids = [item.faq_id for item in items]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"파일 간 중복된 faq_id: {sorted(duplicates)}")
    return items
