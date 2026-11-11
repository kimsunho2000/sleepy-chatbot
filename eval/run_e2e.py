"""전체 응답 평가 (LLM 호출). 결과 JSON과 사람 채점용 CSV를 저장한다.

사용법 (backend/ 에서):
    uv run python ../eval/run_e2e.py --config configs/rag/default.yaml --input-price 0.1 --output-price 0.5
"""

import argparse
import asyncio
import csv
import json
from datetime import datetime

from common import DEFAULT_DATASET, RESULTS_DIR, close_impl, load_dataset, load_impl, load_run_info
from metrics import e2e_metrics

GRADES = "정답 / 부분 정답 / 오답 / 근거 없는 답변"


async def run(system, dataset: list[dict]) -> list[dict]:
    rows = []
    for item in dataset:
        # 후속 질문 문항은 앞선 고객 질문만 넘긴다 (프론트엔드가 보내는 것과 같은 형태)
        history = [h["content"] for h in item.get("history", []) if h["role"] == "user"]
        if history:
            response = await system.aanswer(item["question"], history=history)
        else:
            response = await system.aanswer(item["question"])
        rows.append({**item, **response.model_dump()})
    return rows


def save(rows: list[dict], metrics: dict, info: dict, name: str) -> tuple[str, str]:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = RESULTS_DIR / f"{name}_{stamp}.json"
    csv_path = RESULTS_DIR / f"{name}_{stamp}.csv"

    json_path.write_text(
        json.dumps(
            {"run_info": info, "metrics": metrics, "rows": rows}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    # Excel에서 한글이 깨지지 않도록 utf-8-sig
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "run",
                "embedding_model",
                "llm_model",
                "id",
                "type",
                "question",
                "expected_mode",
                "mode",
                "answer",
                "sources",
                "retrieved",
                "reason",
                "grade",
                "note",
            ]
        )
        for r in rows:
            sources = ", ".join(f"{s['faq_id']}({s['score']:.2f})" for s in r["sources"])
            retrieved = ", ".join(
                f"{i}({s:.2f})"
                for i, s in zip(
                    r.get("retrieved_ids", []), r.get("retrieved_scores", []), strict=False
                )
            )
            writer.writerow(
                [
                    info["run"],
                    info["embedding_model"],
                    info["llm_model"],
                    r["id"],
                    r["type"],
                    r["question"],
                    r["expected_mode"],
                    r["mode"],
                    r["answer"],
                    sources,
                    retrieved,
                    r.get("reason", ""),
                    "",
                    "",
                ]
            )
    return str(json_path), str(csv_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="전체 응답 평가")
    parser.add_argument("--impl", default="rag.pipeline:create")
    parser.add_argument("--config", required=True)
    parser.add_argument("--name", default=None, help="결과 파일 이름 (기본: 설정 파일 이름)")
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        help="평가 세트 jsonl (기본: eval/dev_dataset.jsonl)",
    )
    parser.add_argument("--input-price", type=float, default=0.0, help="입력 100만 토큰당 USD")
    parser.add_argument("--output-price", type=float, default=0.0, help="출력 100만 토큰당 USD")
    args = parser.parse_args()

    dataset_path = args.dataset
    info = load_run_info(args.impl, args.config, dataset_path)
    print(f"[{info['run']}] 임베딩: {info['embedding_model']} / LLM: {info['llm_model']}")
    dataset = load_dataset(dataset_path)
    system = load_impl(args.impl, args.config)
    try:
        rows = asyncio.run(run(system, dataset))
    finally:
        close_impl(system)

    metrics = e2e_metrics(rows, args.input_price, args.output_price)
    name = args.name or args.config.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".yaml")
    json_path, csv_path = save(rows, metrics, info, name)

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"결과: {json_path}")
    print(f"채점용 CSV: {csv_path}  (grade 열에 {GRADES} 중 하나 입력)")


if __name__ == "__main__":
    main()
