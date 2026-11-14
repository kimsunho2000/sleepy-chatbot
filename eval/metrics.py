"""평가 지표 계산."""

from collections.abc import Callable

ANSWERED = {"answer", "partial"}
REFUSED = {"unknown", "offtopic"}


def first_hit_rank(retrieved_ids: list[str], expected_ids: list[str]) -> int | None:
    for rank, faq_id in enumerate(retrieved_ids, start=1):
        if faq_id in expected_ids:
            return rank
    return None


def retrieval_hit(row: dict) -> bool:
    """정답 FAQ가 판단 전 검색 후보에 들어 있었는지."""
    return any(faq_id in row["expected_faq_ids"] for faq_id in row.get("retrieved_ids", []))


def retrieval_metrics(rows: list[dict], ks: tuple[int, ...] = (1, 3, 5)) -> dict:
    """rows: {expected_faq_ids, retrieved_ids}. 정답 FAQ가 있는 질문만 넣는다."""
    n = len(rows)
    if n == 0:
        return {}
    ranks = [first_hit_rank(r["retrieved_ids"], r["expected_faq_ids"]) for r in rows]
    result = {f"hit@{k}": sum(1 for r in ranks if r and r <= k) / n for k in ks}
    result["mrr"] = sum(1 / r for r in ranks if r) / n
    result["n"] = n
    return result


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))
    return ordered[index]


def rate(rows: list[dict], predicate: Callable[[dict], bool]) -> float | None:
    """조건을 만족하는 비율. 해당 문항이 없으면 0이 아니라 None (0%로 오해하지 않도록)."""
    return sum(predicate(r) for r in rows) / len(rows) if rows else None


def e2e_metrics(rows: list[dict], input_price: float = 0.0, output_price: float = 0.0) -> dict:
    """rows: 평가 문항 + 응답(mode, sources, retrieved_ids, latency_ms, *_tokens).

    가격은 100만 토큰당 달러.
    """
    should_answer = [r for r in rows if r["expected_mode"] == "answer"]
    should_partial = [r for r in rows if r["expected_mode"] == "partial"]
    should_refuse = [r for r in rows if r["expected_mode"] in REFUSED]
    answered_ok = [r for r in should_answer if r["mode"] in ANSWERED]
    # 검색 후보를 기록하지 않는 구현도 있으므로 기록된 응답만 센다
    with_retrieval = [r for r in rows if r["expected_faq_ids"] and r.get("retrieved_ids")]

    n = len(rows) or 1
    # RAG 장애로 답하지 못한 행(mode=error)은 지연 0으로 기록되므로 지연 통계에서 뺀다
    latencies = [r["latency_ms"] for r in rows if r["mode"] != "error"]
    prompt_tokens = sum(r["prompt_tokens"] for r in rows)
    completion_tokens = sum(r["completion_tokens"] for r in rows)
    cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000

    return {
        "n": len(rows),
        "error_count": sum(r["mode"] == "error" for r in rows),
        "mode_accuracy": sum(r["mode"] == r["expected_mode"] for r in rows) / n,
        # 답하면 안 되는 질문에 답한 비율 (근거 없는 답변 위험)
        "wrong_answer_rate": rate(should_refuse, lambda r: r["mode"] in ANSWERED),
        # 답할 수 있는 질문을 거절한 비율
        "false_refusal_rate": rate(should_answer, lambda r: r["mode"] in REFUSED),
        # partial이어야 하는데 거절한 비율 (답할 수 있는 부분까지 버림)
        "partial_refusal_rate": rate(should_partial, lambda r: r["mode"] in REFUSED),
        # partial이어야 하는데 answer로 답한 비율 (모르는 부분 안내를 빠뜨렸거나 지어냈을 수 있음)
        "partial_overclaim_rate": rate(should_partial, lambda r: r["mode"] == "answer"),
        # 검색 실패와 판단 실패를 구분하기 위한 지표
        "retrieval_hit_rate": rate(with_retrieval, retrieval_hit),
        # 답한 경우 출처에 정답 FAQ가 들어 있는 비율
        "source_hit_rate": rate(
            answered_ok,
            lambda r: any(s["faq_id"] in r["expected_faq_ids"] for s in r["sources"]),
        ),
        "latency_avg_ms": sum(latencies) / len(latencies) if latencies else None,
        "latency_p95_ms": percentile(latencies, 95),
        "tokens_per_question": (prompt_tokens + completion_tokens) / n,
        "cost_per_question_usd": cost / n,
    }
