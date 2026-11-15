"""FAQ를 Qdrant에 적재한다. QDRANT_URL이 있으면 Qdrant Cloud, 없으면 로컬 모드.

FAQ 하나를 "질문 + 답변" 텍스트 하나로 임베딩한다 (FAQ 1개 = 청크 1개).
질문만 임베딩하면 답변에만 나오는 단어("USB-C", "방수")로 묻는 질문을 놓친다.

사용법 (backend/ 에서):
    uv run python -m rag.indexer --config configs/rag/default.yaml

Qdrant Cloud에 올릴 때는 .env의 QDRANT_URL·QDRANT_API_KEY를 채우고 같은 명령을 실행한다.
다시 올리는 동안(컬렉션 삭제 → 생성) 서버 검색이 잠시 실패한다.
"""

import argparse
import hashlib
import shutil
import uuid

from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from rag.config import RagConfig, Settings, load_config, resolve_path
from rag.data_loader import load_confirmed_items

# 인덱스를 만든 데이터·임베딩 모델 값을 컬렉션 메타데이터의 이 키에 남긴다.
# 파일 대신 컬렉션에 두어 로컬 모드와 Qdrant Cloud에서 같은 방식으로 확인한다
SIGNATURE_KEY = "index_signature"


def make_qdrant_client(config: RagConfig, settings: Settings) -> QdrantClient:
    if settings.qdrant_url:
        api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
        return QdrantClient(url=settings.qdrant_url, api_key=api_key)
    config.qdrant_path.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(config.qdrant_path))


def build_embeddings(config: RagConfig, settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=config.embedding.model, api_key=settings.openai_api_key)


def index_signature(config: RagConfig) -> dict:
    """인덱스가 현재 데이터·임베딩 모델과 맞는지 확인하는 데 쓰는 값."""
    # 추가 데이터가 없으면 예전과 같은 값이 나오도록 파일 내용을 순서대로 이어 해시한다
    data = b"".join(resolve_path(p).read_bytes() for p in config.data_paths)
    # Windows 체크아웃(CRLF)에서 올린 인덱스를 Linux 서버(LF)에서도 같은 데이터로 보도록 맞춘다
    data = data.replace(b"\r\n", b"\n")
    return {
        "data_sha256": hashlib.sha256(data).hexdigest(),
        "embedding_model": config.embedding.model,
    }


def build_index(config: RagConfig, settings: Settings) -> int:
    items = load_confirmed_items(config.data_paths)
    embeddings = build_embeddings(config, settings)
    texts = [f"{item.question}\n{item.answer}" for item in items]
    metadatas = [
        {
            "faq_id": item.faq_id,
            "question": item.question,
            "answer": item.answer,
            "category": item.category,
            "support_required": item.support_required,
        }
        for item in items
    ]

    if not settings.qdrant_url:
        # 로컬 모드는 컬렉션을 지웠다 다시 만들어도 예전 포인트가 남아(qdrant-client 1.20)
        # 다시 인덱싱할 때마다 FAQ가 중복된다. 폴더째 지우고 새로 만든다
        shutil.rmtree(config.qdrant_path, ignore_errors=True)
    client = make_qdrant_client(config, settings)
    try:
        dim = len(embeddings.embed_query("dimension check"))
        if client.collection_exists(config.collection_name):
            client.delete_collection(config.collection_name)
        client.create_collection(
            config.collection_name,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            metadata={SIGNATURE_KEY: index_signature(config)},
        )
        store = QdrantVectorStore(
            client=client, collection_name=config.collection_name, embedding=embeddings
        )
        # FAQ ID로 포인트 ID를 정해, 같은 FAQ를 다시 올리면 새로 늘지 않고 덮어쓰게 한다
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, item.faq_id)) for item in items]
        store.add_texts(texts, metadatas=metadatas, ids=ids)
        count = client.count(config.collection_name).count
    finally:
        client.close()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="FAQ를 Qdrant에 인덱싱한다.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = load_config(args.config)
    settings = Settings()
    count = build_index(config, settings)
    target = settings.qdrant_url or config.qdrant_path
    print(f"[{config.name}] {count}개 포인트 저장 → {target} ({config.collection_name})")


if __name__ == "__main__":
    main()
