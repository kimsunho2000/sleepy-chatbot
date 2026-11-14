"""업무 DB 테이블 5개 (docs/admin-chat-erd.md). 테이블 생성·변경은 Alembic 마이그레이션으로 한다."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 제약 이름을 고정해 두면 마이그레이션에서 이름으로 찾고 지울 수 있다
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TURN_STATUSES = ("completed", "failed")
TURN_MODES = ("answer", "partial", "unknown", "offtopic", "greeting")
TURN_ERROR_CODES = (
    "llm_rate_limit",
    "llm_quota",
    "llm_timeout",
    "llm_parse_error",
    "llm_error",
    "retrieval_error",
)
SOURCE_KINDS = ("retrieved", "cited")
RATINGS = ("up", "down")
FEEDBACK_REASONS = ("wrong", "insufficient", "irrelevant")
INQUIRY_ORIGINS = ("uncertain_answer_card", "agent_request", "direct_form")
INQUIRY_STATUSES = ("received", "in_progress", "completed")


def _in(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# 문의 표시 번호 INQ-1001부터. 권한과는 관계없다
INQUIRY_REFERENCE_SEQ = Sequence("inquiry_reference_seq", start=1001, metadata=Base.metadata)


class Chat(Base):
    __tablename__ = "chat"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    client_ip_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_chat_client_ip_hash_created_at", "client_ip_hash", "created_at"),)


class ChatTurn(Base):
    __tablename__ = "chat_turn"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat.id"))
    parent_turn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_turn.id"))
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    mode: Mapped[str | None] = mapped_column(String(16))
    answer: Mapped[str | None] = mapped_column(Text)
    show_contact: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    reason: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(32))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    llm_model: Mapped[str] = mapped_column(String(100))
    config_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in("status", TURN_STATUSES), name="status"),
        CheckConstraint(f"mode IS NULL OR {_in('mode', TURN_MODES)}", name="mode"),
        CheckConstraint(
            f"error_code IS NULL OR {_in('error_code', TURN_ERROR_CODES)}", name="error_code"
        ),
        # 완료 turn은 판단과 답변이 있고, 실패 turn은 원인만 있다. 장애를 unknown으로 저장하지 않는다
        CheckConstraint(
            "(status = 'completed' AND mode IS NOT NULL AND answer IS NOT NULL"
            " AND error_code IS NULL)"
            " OR (status = 'failed' AND error_code IS NOT NULL AND mode IS NULL"
            " AND answer IS NULL)",
            name="status_fields",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_ms"),
        CheckConstraint("prompt_tokens IS NULL OR prompt_tokens >= 0", name="prompt_tokens"),
        CheckConstraint(
            "completion_tokens IS NULL OR completion_tokens >= 0", name="completion_tokens"
        ),
        Index("ix_chat_turn_chat_id_created_at", "chat_id", "created_at"),
        Index("ix_chat_turn_chat_id_finished_at", "chat_id", "finished_at"),
        Index("ix_chat_turn_created_at", "created_at"),
        Index("ix_chat_turn_mode_created_at", "mode", "created_at"),
        Index("ix_chat_turn_status_created_at", "status", "created_at"),
    )


class TurnSource(Base):
    __tablename__ = "turn_source"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    turn_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_turn.id"))
    kind: Mapped[str] = mapped_column(String(16))
    rank: Mapped[int] = mapped_column(Integer)
    source_id: Mapped[str] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint(_in("kind", SOURCE_KINDS), name="kind"),
        CheckConstraint("rank >= 1", name="rank"),
        UniqueConstraint("turn_id", "kind", "rank", name="uq_turn_source_turn_kind_rank"),
        UniqueConstraint("turn_id", "kind", "source_id", name="uq_turn_source_turn_kind_source"),
        Index("ix_turn_source_kind_source_id", "kind", "source_id"),
    )


class Feedback(Base):
    __tablename__ = "feedback"

    turn_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_turn.id"), primary_key=True)
    rating: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in("rating", RATINGS), name="rating"),
        CheckConstraint(
            f"reason IS NULL OR (rating = 'down' AND {_in('reason', FEEDBACK_REASONS)})",
            name="reason",
        ),
        Index("ix_feedback_rating", "rating"),
    )


class Inquiry(Base):
    __tablename__ = "inquiry"
    # 시퀀스로 채운 reference_no를 INSERT ... RETURNING으로 바로 받는다
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reference_no: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'INQ-' || nextval('inquiry_reference_seq')"),
    )
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    chat_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat.id"))
    trigger_turn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_turn.id"))
    context_last_turn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chat_turn.id"))
    name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(254))
    content: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(16), default="received", server_default=text("'received'")
    )
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    internal_note: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in("origin", INQUIRY_ORIGINS), name="origin"),
        CheckConstraint(_in("status", INQUIRY_STATUSES), name="status"),
        CheckConstraint("trigger_turn_id IS NULL OR chat_id IS NOT NULL", name="trigger_chat"),
        CheckConstraint("context_last_turn_id IS NULL OR chat_id IS NOT NULL", name="context_chat"),
        CheckConstraint("origin <> 'agent_request' OR chat_id IS NOT NULL", name="agent_chat"),
        CheckConstraint(
            "origin <> 'uncertain_answer_card' OR trigger_turn_id IS NOT NULL", name="card_trigger"
        ),
        CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at"),
        Index("ix_inquiry_status_created_at", "status", "created_at"),
        Index("ix_inquiry_first_viewed_at", "first_viewed_at"),
        Index("ix_inquiry_trigger_turn_id", "trigger_turn_id"),
    )
