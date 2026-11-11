"""2글자 단위 키워드 검색 (BM25). 외부 패키지 없이 메모리에서 계산한다.

임베딩 검색은 질문에 다른 말이 많으면 핵심 단어("음악")가 묻혀 정답 FAQ를 놓칠 때가 있다.
한국어는 조사가 붙어 띄어쓰기 단위로는 "음악도"와 "음악이나"가 다른 단어가 되므로,
어절 안에서 2글자씩 잘라 겹치는 정도를 본다. FAQ가 수백 개 수준이라 매 질문마다 전부 계산해도 충분히 빠르다.
"""

import math
import re
from collections import Counter

WORD_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


def bigrams(text: str) -> list[str]:
    tokens: list[str] = []
    for word in WORD_PATTERN.findall(text.lower()):
        if len(word) == 1:
            tokens.append(word)
        tokens += [word[i : i + 2] for i in range(len(word) - 1)]
    return tokens


class KeywordIndex:
    def __init__(self, docs: dict[str, str], k1: float = 1.2, b: float = 0.75) -> None:
        """docs: {faq_id: 검색 대상 텍스트}"""
        self.k1, self.b = k1, b
        self.tf = {doc_id: Counter(bigrams(text)) for doc_id, text in docs.items()}
        self.length = {doc_id: sum(c.values()) for doc_id, c in self.tf.items()}
        self.avg_length = sum(self.length.values()) / max(1, len(self.length))
        df = Counter(token for counts in self.tf.values() for token in counts)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> dict[str, float]:
        terms = set(bigrams(query))
        result: dict[str, float] = {}
        for doc_id, tf in self.tf.items():
            norm = self.k1 * (1 - self.b + self.b * self.length[doc_id] / self.avg_length)
            result[doc_id] = sum(
                self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm) for t in terms if t in tf
            )
        return result

    def rank(self, query: str) -> list[str]:
        """점수가 0보다 큰 문서만, 높은 순서로."""
        scored = self.scores(query)
        return [d for d in sorted(scored, key=scored.__getitem__, reverse=True) if scored[d] > 0]
