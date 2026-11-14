"""여러 결과 파일(같은 설정을 여러 번 돌린 것)을 모아 설정끼리 비교한다. API 호출 없음.

결과 파일에 저장된 기대값이 아니라 지금의 평가 세트 라벨로 다시 채점한다.
라벨을 고친 뒤에도 예전 결과를 같은 기준으로 비교할 수 있게 하기 위해서다.
LLM 판단은 실행마다 조금씩 달라지므로 같은 설정을 여러 번 돌려 평균과 문항별 일관성을 본다.

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
from metrics import e2e_metrics, retrieval_hit

SHOWN = [
    ("mode_accuracy", "정확도"),
    ("false_refusal_rate", "잘못 거절"),
    ("wrong_answer_rate", "근거 없는 답"),
    ("partial_refusal_rate", "partial→거절"),
    ("partial_overclaim_rate", "partial→answer"),
    ("retrieval_hit_rate", "검색 적중"),
]

Runs = list[list[dict]]  # 결과 파일(회차)마다 행 목록


def load_group(pattern: str, labels: dict[str, dict]) -> Runs:
    """패턴에 맞는 결과 파일을 읽고, 기대값은 현재 평가 세트 라벨로 덮어쓴다."""
    runs = []
    for path in sorted(glob.glob(pattern)):
        if not path.endswith(".json"):
            continue
        rows = json.loads(Path(path).read_text(encoding="utf-8"))["rows"]
        runs.append([{**r, **labels[r["id"]]} for r in rows if r["id"] in labels])
    return runs


def mean_percent(values: list[float | None]) -> str:
    present = [v for v in values if v is not None]
    return f"{statistics.mean(present):.1%}" if present else "-"


def print_summary(groups: dict[str, Runs]) -> None:
    header = f"{'설정':12s} {'회차':>4s} " + " ".join(f"{label:>14s}" for _, label in SHOWN)
    print(header + f" {'응답(초)':>8s}")
    for name, runs in groups.items():
        if not runs:
            print(f"{name:12s} 결과 파일 없음")
            continue
        metrics = [e2e_metrics(rows) for rows in runs]
        cells = " ".join(f"{mean_percent([m[key] for m in metrics]):>14s}" for key, _ in SHOWN)
        # 모든 문항이 RAG 장애로 실패한 회차는 지연 평균이 없다
        latencies = [m["latency_avg_ms"] for m in metrics if m["latency_avg_ms"] is not None]
        latency = f"{statistics.mean(latencies) / 1000:>8.2f}" if latencies else f"{'-':>8s}"
        print(f"{name:12s} {len(runs):>4d} {cells} {latency}")


def print_failures(items: list[dict], groups: dict[str, Runs]) -> None:
    """한 번이라도 틀린 문항만, 설정마다 맞은 횟수와 실제 판단을 보여 준다."""
    print("\n하나라도 틀린 문항 (맞은 횟수/회차, 검색 후보에 정답 FAQ가 있던 횟수)")
    for item in items:
        lines = []
        has_wrong = False
        for name, runs in groups.items():
            rows = [r for run in runs for r in run if r["id"] == item["id"]]
            if not rows:
                continue
            correct = sum(r["mode"] == r["expected_mode"] for r in rows)
            has_wrong |= correct < len(rows)
            checked = [r for r in rows if r["expected_faq_ids"] and r.get("retrieved_ids")]
            hit = f" 검색{sum(map(retrieval_hit, checked))}/{len(checked)}" if checked else ""
            modes = ",".join(r["mode"] for r in rows)
            lines.append(f"{name} {correct}/{len(rows)}{hit} [{modes}]")
        if has_wrong:
            print(f"  {item['id']} (정답 {item['expected_mode']}) {item['question'][:30]}")
            for line in lines:
                print(f"      {line}")


def main() -> None:
    parser = argparse.ArgumentParser(description="결과 파일 묶음 비교")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--group", action="append", required=True, help="이름=결과 파일 glob")
    args = parser.parse_args()

    items = load_dataset(args.dataset)
    labels = {
        i["id"]: {k: i[k] for k in ("expected_mode", "expected_faq_ids", "question")} for i in items
    }
    groups = {}
    for spec in args.group:
        name, pattern = spec.split("=", 1)
        groups[name] = load_group(pattern, labels)

    print(f"평가 세트: {args.dataset} ({len(items)}문항)\n")
    print_summary(groups)
    print_failures(items, groups)


if __name__ == "__main__":
    main()
