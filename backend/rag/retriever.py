"""FAQ 검색: 임베딩 검색 + (선택) 키워드 검색 자리.

langchain-qdrant에는 native async가 없으므로 동기 함수로 두고,
비동기 코드에서는 asyncio.to_thread로 감싸서 호출한다.
"""

import json

from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from rag.config import RagConfig, Settings
from rag.data_loader import load_confirmed_faq
from rag.indexer import META_FILE, build_embeddings, index_signature
from rag.keyword import KeywordIndex
from rag.schemas import Source


class IndexOutdatedError(RuntimeError):
    pass


class Retriever:
    def __init__(self, config: RagConfig, settings: Settings) -> None:
        self._check_index(config)
        self.config = config
        self.client = QdrantClient(path=str(config.qdrant_path))
        self.store = QdrantVectorStore(
            client=self.client,
            collection_name=config.collection_name,
            embedding=build_embeddings(config, settings),
        )
        items = load_confirmed_faq(config.data_path)
        self._faq_count = len(items)
        self.support_required_ids = {i.faq_id for i in items if i.support_required}
        self.keyword_index = (
            KeywordIndex({i.faq_id: f"{i.question} {i.answer}" for i in items})
            if config.retrieval.keyword_slots
            else None
        )

    @staticmethod
    def _check_index(config: RagConfig) -> None:
        meta_path = config.qdrant_path / META_FILE
        if not meta_path.exists():
            raise IndexOutdatedError(
                "인덱스가 없습니다. 먼저 실행하세요: "
                f"uv run python -m rag.indexer --config <설정 파일> (name={config.name})"
            )
        saved = json.loads(meta_path.read_text(encoding="utf-8"))
        if saved != index_signature(config):
            # FAQ가 바뀌었는데 예전 인덱스로 답하는 것을 막는다
            raise IndexOutdatedError(
                f"데이터나 임베딩 모델이 바뀌었습니다. 인덱서를 다시 실행하세요 (name={config.name})"
            )

    def search(self, question: str, k: int) -> list[Source]:
        """상위 k개 FAQ. keyword_slots만큼은 임베딩 상위에 없는 키워드 검색 1등에게 내준다."""
        slots = min(self.config.retrieval.keyword_slots, k - 1)
        if not self.keyword_index or slots <= 0:
            return self._dense(question, k)

        # 키워드로 고른 FAQ에도 코사인 점수가 필요해서(min_score 필터, 출처 표시) 전체 순위를 받는다.
        # 임베딩 호출은 그대로 1회이고, FAQ 수백 개 규모에서는 로컬 검색 비용이 무시할 만하다.
        dense = self._dense(question, self._faq_count)
        head = dense[: k - slots]
        chosen = {s.faq_id for s in head}
        by_id = {s.faq_id: s for s in dense}
        extra = [by_id[i] for i in self.keyword_index.rank(question) if i not in chosen][:slots]
        chosen |= {s.faq_id for s in extra}
        # 겹치는 단어가 없어 키워드 결과가 모자라면 임베딩 다음 순위로 채운다
        rest = [s for s in dense[k - slots :] if s.faq_id not in chosen]
        return (head + extra + rest)[:k]

    def _dense(self, question: str, k: int) -> list[Source]:
        """코사인 유사도(높을수록 유사) 기준 상위 k개 FAQ."""
        hits = self.store.similarity_search_with_score(question, k=k)
        return [
            Source(
                faq_id=doc.metadata["faq_id"],
                title=doc.metadata["question"],
                category=doc.metadata["category"],
                score=float(score),
                excerpt=doc.metadata["answer"],
            )
            for doc, score in hits
        ]

    def close(self) -> None:
        self.client.close()
