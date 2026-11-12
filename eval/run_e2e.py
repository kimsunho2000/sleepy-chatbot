"""전체 응답 평가 (LLM 호출). 결과 JSON과 사람 채점용 CSV를 저장한다.

사용법 (backend/ 에서):
    uv run python ../eval/run_e2e.py --config configs/rag/default.yaml --input-price 0.1 --output-price 0.5
"""

import argparse
import asyncio
import csv
import json
from datetime import datetime
from pathlib import Path

from common import (
    DEFAULT_DATASET,
    RESULTS_DIR,
    close_impl,
    load_dataset,
    load_impl,
    load_run_info,
    previous_questions,
)
from metrics import e2e_metrics

from rag.schemas import RagSystem

GRADES = "정답 / 부분 정답 / 오답 / 근거 없는 답변"
CSV_COLUMNS = [
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
    "grade",  # 사람이 채점할 칸
    "note",
]


async def run(system: RagSystem, dataset: list[dict]) -> list[dict]:
    rows = []
    for item in dataset:
        history = previous_questions(item)
        # 이전 질문을 받지 않는 구현도 평가할 수 있도록, 이전 질문이 있을 때만 넘긴다
        if history:
            response = await system.aanswer(item["question"], history=history)
        else:
            response = await system.aanswer(item["question"])
        rows.append({**item, **response.model_dump()})
    return rows


def csv_row(row: dict, info: dict) -> list[str]:
    sources = ", ".join(f"{s['faq_id']}({s['score']:.2f})" for s in row["sources"])
    retrieved = ", ".join(
        f"{faq_id}({score:.2f})"
        for faq_id, score in zip(
            row.get("retrieved_ids", []), row.get("retrieved_scores", []), strict=False
        )
    )
    return [
        info["run"],
        info["embedding_model"],
        info["llm_model"],
        row["id"],
        row["type"],
        row["question"],
        row["expected_mode"],
        row["mode"],
        row["answer"],
        sources,
        retrieved,
        row.get("reason", ""),
        "",
        "",
    ]


def save(rows: list[dict], metrics: dict, info: dict, name: str) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = RESULTS_DIR / f"{name}_{stamp}.json"
    csv_path = RESULTS_DIR / f"{name}_{stamp}.csv"

    result = {"run_info": info, "metrics": metrics, "rows": rows}
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    # Excel에서 한글이 깨지지 않도록 utf-8-sig
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(csv_row(r, info) for r in rows)
    return json_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="전체 응답 평가")
    parser.add_argument("--impl", default="rag.pipeline:create")
    parser.add_argument("--config", required=True)
    parser.add_argument("--name", default=None, help="결과 파일 이름 (기본: 설정 파일 이름)")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="평가 세트 jsonl")
    parser.add_argument("--input-price", type=float, default=0.0, help="입력 100만 토큰당 USD")
    parser.add_argument("--output-price", type=float, default=0.0, help="출력 100만 토큰당 USD")
    args = parser.parse_args()

    info = load_run_info(args.impl, args.config, args.dataset)
    print(f"[{info['run']}] 임베딩: {info['embedding_model']} / LLM: {info['llm_model']}")
    dataset = load_dataset(args.dataset)
    system = load_impl(args.impl, args.config)
    try:
        rows = asyncio.run(run(system, dataset))
    finally:
        close_impl(system)

    metrics = e2e_metrics(rows, args.input_price, args.output_price)
    json_path, csv_path = save(rows, metrics, info, args.name or Path(args.config).stem)

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"결과: {json_path}")
    print(f"채점용 CSV: {csv_path}  (grade 열에 {GRADES} 중 하나 입력)")


if __name__ == "__main__":
    main()
