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


async def run(system, dataset: list[dict], k: int) -> list[dict]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="검색 단계 평가")
    parser.add_argument("--impl", default="rag.pipeline:create")
    parser.add_argument("--config", required=True)
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        help="평가 세트 jsonl (기본: eval/dev_dataset.jsonl)",
    )
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--verbose", action="store_true", help="질문별 결과 출력")
    args = parser.parse_args()

    dataset_path = args.dataset
    info = load_run_info(args.impl, args.config, dataset_path)
    print(f"[{info['run']}] 임베딩: {info['embedding_model']}")
    dataset = load_dataset(dataset_path)
    system = load_impl(args.impl, args.config)
    try:
        rows = asyncio.run(run(system, dataset, args.k))
    finally:
        close_impl(system)

    normal = [r for r in rows if r["expected_faq_ids"]]
    print(json.dumps(retrieval_metrics(normal), ensure_ascii=False, indent=2))

    # 임계값을 정할 때 참고: 답할 질문과 거절할 질문의 top1 점수 분포
    for label, group in (
        ("정답 있는 질문", normal),
        ("정답 없는 질문", [r for r in rows if not r["expected_faq_ids"]]),
    ):
        tops = sorted(r["scores"][0] for r in group if r["scores"])
        if tops:
            print(
                f"{label} top1 점수: 최소 {tops[0]:.3f} / 중앙 {tops[len(tops) // 2]:.3f} / 최대 {tops[-1]:.3f}"
            )

    if args.verbose:
        for r in rows:
            rank = first_hit_rank(r["retrieved_ids"], r["expected_faq_ids"])
            print(f"{r['id']}\t{rank}\t{r['retrieved_ids']}\t{r['scores']}\t{r['question']}")


if __name__ == "__main__":
    main()
