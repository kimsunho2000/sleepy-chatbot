"""RAG가 답변을 만들지 못한 시스템 장애.

근거가 없어 답하지 못한 것(mode=unknown)과 구별한다. 호출하는 쪽(백엔드 Service)은
이 예외로 실패 turn을 저장하고, 고객에게는 일시적 장애로 안내한다.
OpenAI API 오류(속도 제한, 크레딧 소진 등)는 감싸지 않고 그대로 올려 보낸다.
"""


class RagError(Exception):
    """RAG 처리 중 장애."""


class RetrievalError(RagError):
    """임베딩 또는 Qdrant 검색 실패."""


class ParseError(RagError):
    """LLM 응답을 정해진 형식으로 해석하지 못함."""
