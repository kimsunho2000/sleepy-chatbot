"""전체 응답 평가 (LLM 호출). 결과 JSON과 사람 채점용 CSV를 저장한다.

사용법 (backend/ 에서):
    uv run python ../eval/run_e2e.py --config configs/rag/default.yaml --input-price 0.1 --output-price 0.5

LLM 답은 실행마다 달라서 한 번 결과로는 판단하기 어렵다. --repeat 3이면 3번 돌려 각각 저장하고,
한 번이라도 기대한 mode를 벗어난 질문을 모아 보여 준다 (모든 시도가 맞아야 통과).
"""

import argparse
import asyncio
import csv
import json
from collections.abc import Callable
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

from rag.errors import RagError
from rag.schemas import RagSystem

# RAG 장애로 답변을 만들지 못한 질문. 응답 필드 모양은 RagResponse와 맞춘다
FAILED_ROW = {
    "mode": "error",
    "answer": "",
    "sources": [],
    "show_contact": False,
    "retrieved_ids": [],
    "retrieved_scores": [],
    "latency_ms": 0.0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
}
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
        try:
            if history:
                response = await system.aanswer(item["question"], history=history)
            else:
                response = await system.aanswer(item["question"])
        except RagError as e:
            # 장애(파싱·검색 실패)는 unknown 답변이 아니라 실패로 기록해 채점에서 구별한다
            rows.append({**item, **FAILED_ROW, "reason": f"{type(e).__name__}: {e}"})
            continue
        rows.append({**item, **response.model_dump()})
    return rows


async def run_many(
    system: RagSystem, dataset: list[dict], repeat: int, on_done: Callable[[int, list[dict]], None]
) -> None:
    """회차가 끝날 때마다 on_done으로 바로 저장해, 뒤 회차가 실패해도 앞 결과가 남게 한다."""
    for attempt in range(1, repeat + 1):
        on_done(attempt, await run(system, dataset))


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
    parser.add_argument("--repeat", type=int, default=1, help="같은 세트를 반복 실행할 횟수")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat은 1 이상이어야 해요")

    info = load_run_info(args.impl, args.config, args.dataset)
    print(f"[{info['run']}] 임베딩: {info['embedding_model']} / LLM: {info['llm_model']}")
    dataset = load_dataset(args.dataset)
    system = load_impl(args.impl, args.config)
    name = args.name or Path(args.config).stem
    all_metrics: list[dict] = []
    # 질문 ID → 기대 mode를 벗어난 시도의 mode 목록
    misses: dict[str, list[str]] = {}

    def save_attempt(attempt: int, rows: list[dict]) -> None:
        metrics = e2e_metrics(rows, args.input_price, args.output_price)
        run_name = name if args.repeat == 1 else f"{name}-r{attempt}"
        json_path, csv_path = save(rows, metrics, info, run_name)
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
        print(f"결과: {json_path}")
        print(f"채점용 CSV: {csv_path}  (grade 열에 {GRADES} 중 하나 입력)")
        all_metrics.append(metrics)
        for row in rows:
            if row["mode"] != row["expected_mode"]:
                misses.setdefault(row["id"], []).append(row["mode"])

    try:
        # 클라이언트가 이벤트 루프에 묶여 있어 반복도 한 루프 안에서 돈다
        asyncio.run(run_many(system, dataset, args.repeat, save_attempt))
    finally:
        close_impl(system)

    if args.repeat > 1:
        summary = repeat_summary(all_metrics)
        print(f"[{args.repeat}회 평균] " + json.dumps(summary, ensure_ascii=False))
        print("한 번이라도 기대 mode를 벗어난 질문 (모든 시도가 맞아야 통과):")
        for item_id, modes in sorted(misses.items()):
            print(f"  {item_id}: {len(modes)}/{args.repeat}회 → {', '.join(modes)}")


def repeat_summary(all_metrics: list[dict]) -> dict:
    """숫자 지표만 평균 낸다."""
    keys = [
        k
        for k, v in all_metrics[0].items()
        if isinstance(v, int | float) and not isinstance(v, bool)
    ]
    return {
        k: round(sum(m[k] for m in all_metrics if m.get(k) is not None) / len(all_metrics), 4)
        for k in keys
        if all(m.get(k) is not None for m in all_metrics)
    }


if __name__ == "__main__":
    main()
