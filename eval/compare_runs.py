"""여러 결과 파일(같은 설정을 여러 번 돌린 것)을 모아 설정끼리 비교한다. API 호출 없음.

결과 파일에 저장된 기대값이 아니라 지금의 평가 세트 라벨로 다시 채점한다.
라벨을 고친 뒤에도 예전 결과를 같은 기준으로 비교할 수 있게 하기 위해서다.

사용법 (backend/ 에서):
    uv run python ../eval/compare_runs.py \\
        --group "기존=../eval/results/default_r*.json" \\
        --group "새 설정=../eval/results/새설정_r*.json"
"""

import argparse
import glob
import json
import statistics
from pathlib import Path

from common import DEFAULT_DATASET, load_dataset
from metrics import e2e_metrics

SHOWN = [
    ("mode_accuracy", "정확도"),
    ("false_refusal_rate", "잘못 거절"),
    ("wrong_answer_rate", "근거 없는 답"),
    ("partial_refusal_rate", "partial→거절"),
    ("partial_overclaim_rate", "partial→answer"),
    ("retrieval_hit_rate", "검색 적중"),
]


def load_group(pattern: str, labels: dict[str, dict]) -> list[list[dict]]:
    """패턴에 맞는 결과 파일마다 행 목록을 돌려준다. 기대값은 현재 평가 세트로 덮어쓴다."""
    runs = []
    for path in sorted(glob.glob(pattern)):
        if not path.endswith(".json"):
            continue
        rows = json.loads(Path(path).read_text(encoding="utf-8"))["rows"]
        rows = [{**r, **labels[r["id"]]} for r in rows if r["id"] in labels]
        runs.append(rows)
    return runs


def fmt(values: list[float | None]) -> str:
    present = [v for v in values if v is not None]
    if not present:
        return "-"
    return f"{statistics.mean(present):.1%}"


def main() -> None:
    parser = argparse.ArgumentParser(description="결과 파일 묶음 비교")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--group", action="append", required=True, help="이름=결과 파일 glob")
    args = parser.parse_args()

    items = load_dataset(args.dataset)
    labels = {
        i["id"]: {k: i[k] for k in ("expected_mode", "expected_faq_ids", "question")} for i in items
    }

    groups: dict[str, list[list[dict]]] = {}
    for spec in args.group:
        name, pattern = spec.split("=", 1)
        groups[name] = load_group(pattern, labels)

    print(f"평가 세트: {args.dataset} ({len(items)}문항)\n")
    header = f"{'설정':12s} {'회차':>4s} " + " ".join(f"{label:>14s}" for _, label in SHOWN)
    print(header + f" {'응답(초)':>8s}")
    for name, runs in groups.items():
        if not runs:
            print(f"{name:12s} 결과 파일 없음")
            continue
        metrics = [e2e_metrics(rows) for rows in runs]
        cells = " ".join(f"{fmt([m[key] for m in metrics]):>14s}" for key, _ in SHOWN)
        latency = statistics.mean(m["latency_avg_ms"] for m in metrics) / 1000
        print(f"{name:12s} {len(runs):>4d} {cells} {latency:>8.2f}")

    # 문항별 일관성: 한 번이라도 틀린 문항만, 설정마다 "맞은 횟수/회차"와 실제 판단
    print("\n하나라도 틀린 문항 (맞은 횟수/회차, 검색 후보에 정답 FAQ가 있던 횟수)")
    for item in items:
        qid = item["id"]
        cells = []
        wrong = False
        for name, runs in groups.items():
            rows = [r for rows in runs for r in rows if r["id"] == qid]
            if not rows:
                continue
            ok = sum(r["mode"] == r["expected_mode"] for r in rows)
            wrong |= ok < len(rows)
            hits = [
                any(i in r["expected_faq_ids"] for i in r["retrieved_ids"])
                for r in rows
                if r["expected_faq_ids"] and r.get("retrieved_ids")
            ]
            hit = f" 검색{sum(hits)}/{len(hits)}" if hits else ""
            modes = ",".join(r["mode"] for r in rows)
            cells.append(f"{name} {ok}/{len(rows)}{hit} [{modes}]")
        if wrong:
            print(f"  {qid} (정답 {item['expected_mode']}) {item['question'][:30]}")
            for cell in cells:
                print(f"      {cell}")


if __name__ == "__main__":
    main()
