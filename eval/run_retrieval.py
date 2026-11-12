"""검색 평가 (LLM 호출 없음, 질문 임베딩만).

사용법 (backend/ 에서):
    uv run python ../eval/run_retrieval.py --config configs/rag/default.yaml
    uv run python ../eval/run_retrieval.py --impl my_rag.pipeline:create --config ...
"""

import argparse
import asyncio
import json

from common import DEFAULT_DATASET, close_impl, load_dataset, load_impl, load_run_info
from metrics import first_hit_rank, retrieval_metrics

from rag.schemas import RagSystem


async def run(system: RagSystem, dataset: list[dict], k: int) -> list[dict]:
    rows = []
    for item in dataset:
        sources = await system.aretrieve(item["question"], k)
        rows.append(
            {
                **item,
                "retrieved_ids": [s.faq_id for s in sources],
                "scores": [round(s.score, 4) for s in sources],
            }
        )
    return rows


def print_top1_scores(rows: list[dict]) -> None:
    """답할 질문과 거절할 질문의 1위 점수 분포. min_score를 정할 때 참고한다."""
    groups = (
        ("정답 있는 질문", [r for r in rows if r["expected_faq_ids"]]),
        ("정답 없는 질문", [r for r in rows if not r["expected_faq_ids"]]),
    )
    for label, group in groups:
        tops = sorted(r["scores"][0] for r in group if r["scores"])
        if tops:
            middle = tops[len(tops) // 2]
            print(f"{label} 1위 점수: 최소 {tops[0]:.3f} / 중앙 {middle:.3f} / 최대 {tops[-1]:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="검색 단계 평가")
    parser.add_argument("--impl", default="rag.pipeline:create")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="평가 세트 jsonl")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--verbose", action="store_true", help="질문별 결과 출력")
    args = parser.parse_args()

    info = load_run_info(args.impl, args.config, args.dataset)
    print(f"[{info['run']}] 임베딩: {info['embedding_model']}")
    dataset = load_dataset(args.dataset)
    system = load_impl(args.impl, args.config)
    try:
        rows = asyncio.run(run(system, dataset, args.k))
    finally:
        close_impl(system)

    answerable = [r for r in rows if r["expected_faq_ids"]]
    print(json.dumps(retrieval_metrics(answerable), ensure_ascii=False, indent=2))
    print_top1_scores(rows)

    if args.verbose:
        for r in rows:
            rank = first_hit_rank(r["retrieved_ids"], r["expected_faq_ids"])
            print(f"{r['id']}\t{rank}\t{r['retrieved_ids']}\t{r['scores']}\t{r['question']}")


if __name__ == "__main__":
    main()
