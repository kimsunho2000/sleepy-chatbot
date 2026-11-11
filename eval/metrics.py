"""평가 지표 계산."""

from collections.abc import Callable

ANSWERED = {"answer", "partial"}
REFUSED = {"unknown", "offtopic"}


def first_hit_rank(retrieved_ids: list[str], expected_ids: list[str]) -> int | None:
    for rank, faq_id in enumerate(retrieved_ids, start=1):
        if faq_id in expected_ids:
            return rank
    return None


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


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1)))
    return ordered[index]


def _rate(rows: list[dict], predicate: Callable[[dict], bool]) -> float | None:
    """해당 문항이 없으면 0이 아니라 None (0%로 오해하지 않도록)."""
    return sum(predicate(r) for r in rows) / len(rows) if rows else None


def e2e_metrics(rows: list[dict], input_price: float = 0.0, output_price: float = 0.0) -> dict:
    """rows: dataset 항목 + 응답(mode, sources, latency_ms, *_tokens).

    가격은 100만 토큰당 달러.
    """
    should_answer = [r for r in rows if r["expected_mode"] == "answer"]
    should_refuse = [r for r in rows if r["expected_mode"] in REFUSED]
    should_partial = [r for r in rows if r["expected_mode"] == "partial"]
    answered_ok = [r for r in should_answer if r["mode"] in ANSWERED]
    # 검색 후보가 기록된 응답만 (예전 구현이나 다른 팀원 구현은 비어 있을 수 있다)
    with_retrieval = [r for r in rows if r["expected_faq_ids"] and r.get("retrieved_ids")]
    latencies = [r["latency_ms"] for r in rows]
    n = len(rows) or 1

    prompt_tokens = sum(r["prompt_tokens"] for r in rows)
    completion_tokens = sum(r["completion_tokens"] for r in rows)
    cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000

    return {
        "n": len(rows),
        "mode_accuracy": sum(r["mode"] == r["expected_mode"] for r in rows) / n,
        # 답하면 안 되는 질문에 답한 비율 (근거 없는 답변 위험)
        "wrong_answer_rate": (
            sum(r["mode"] in ANSWERED for r in should_refuse) / len(should_refuse)
            if should_refuse
            else 0.0
        ),
        # 답할 수 있는 질문을 거절한 비율
        "false_refusal_rate": (
            sum(r["mode"] in REFUSED for r in should_answer) / len(should_answer)
            if should_answer
            else 0.0
        ),
        # partial이어야 하는데 거절한 비율 (답할 수 있는 부분까지 버림)
        "partial_refusal_rate": _rate(should_partial, lambda r: r["mode"] in REFUSED),
        # partial이어야 하는데 answer로 답한 비율 (모르는 부분 안내를 빠뜨렸거나 지어냈을 수 있음)
        "partial_overclaim_rate": _rate(should_partial, lambda r: r["mode"] == "answer"),
        # 정답 FAQ가 판단 전 검색 후보에 들어 있던 비율 (검색 실패와 판단 실패 구분용)
        "retrieval_hit_rate": _rate(
            with_retrieval,
            lambda r: any(i in r["expected_faq_ids"] for i in r["retrieved_ids"]),
        ),
        # 답한 경우 출처에 정답 FAQ가 들어 있는 비율
        "source_hit_rate": (
            sum(
                any(s["faq_id"] in r["expected_faq_ids"] for s in r["sources"]) for r in answered_ok
            )
            / len(answered_ok)
            if answered_ok
            else 0.0
        ),
        "latency_avg_ms": sum(latencies) / n,
        "latency_p95_ms": percentile(latencies, 95),
        "tokens_per_question": (prompt_tokens + completion_tokens) / n,
        "cost_per_question_usd": cost / n,
    }
