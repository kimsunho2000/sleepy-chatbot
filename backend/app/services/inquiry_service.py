"""문의 접수: 대화 연결 규칙, 중복 접수 방지(request_id), 채팅 기록 경계."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AppSettings
from app.core.errors import AppError, ErrorCode
from app.core.rate_limit import SlidingWindowLimiter
from app.db.models import Chat, Inquiry
from app.repositories.chat_repository import ChatRepository
from app.repositories.inquiry_repository import InquiryRepository
from app.schemas.inquiry import InquiryRequest, InquiryResponse
from app.services.access import authorize_chat, enforce_limit

HOUR = 3600


def _invalid(message: str, field: str) -> AppError:
    return AppError(ErrorCode.VALIDATION_ERROR, message, fields=[field])


def _response(inquiry: Inquiry) -> InquiryResponse:
    return InquiryResponse(
        inquiry_id=inquiry.id,
        reference_no=inquiry.reference_no,
        # 재전송에는 "처음 결과"를 돌려준다. 접수 직후 상태는 항상 received라서
        # 관리자가 이후 상태를 바꿨어도 고객에게 처리 상태가 새어 나가지 않는다
        status="received",
        created_at=inquiry.created_at,
    )


def _same_request(inquiry: Inquiry, request: InquiryRequest) -> bool:
    return (
        inquiry.name == request.name
        and inquiry.email == request.email
        and inquiry.content == request.content
        and inquiry.origin == request.origin
        and inquiry.chat_id == request.chat_id
        and inquiry.trigger_turn_id == request.trigger_turn_id
    )


class InquiryService:
    def __init__(
        self, session: AsyncSession, settings: AppSettings, limiter: SlidingWindowLimiter
    ) -> None:
        self.session = session
        self.settings = settings
        self.limiter = limiter
        self.chats = ChatRepository(session)
        self.inquiries = InquiryRepository(session)

    async def create(
        self, request: InquiryRequest, token: str | None, client_ip_hash: str
    ) -> InquiryResponse:
        chat = await self._chat(request, token)

        # 같은 request_id는 새로 만들지 않고 처음 결과를 돌려준다 (버튼 연타, 재전송)
        existing = await self.inquiries.get_by_request_id(request.request_id)
        if existing is not None:
            return self._replay(existing, request)

        await self._check_links(request, chat)
        # 입력 오류(422)로 거절된 요청은 한도에 넣지 않는다
        enforce_limit(
            self.limiter,
            f"inquiry:ip:{client_ip_hash}",
            self.settings.inquiry_per_ip_per_hour,
            HOUR,
            # 같은 문의를 동시에 다시 보내도 한도는 한 번만 쓴다
            request_key=str(request.request_id),
        )

        if chat is not None:
            # 같은 대화의 turn 저장과 한 줄로 세워, 경계 뒤에 저장되는 turn이 기록에 끼어들지 않게 한다
            await self.chats.lock_chat(chat.id)
        now = datetime.now(UTC)
        inquiry = Inquiry(
            id=uuid.uuid4(),
            request_id=request.request_id,
            chat_id=chat.id if chat else None,
            trigger_turn_id=request.trigger_turn_id,
            context_last_turn_id=await self.chats.last_saved_turn_id(chat.id) if chat else None,
            name=request.name,
            email=request.email,
            content=request.content,
            origin=request.origin,
            status="received",
            internal_note="",
            created_at=now,
            updated_at=now,
        )
        try:
            await self.inquiries.add(inquiry)
            await self.session.commit()
        except IntegrityError:
            # 같은 request_id가 동시에 들어와 먼저 저장된 경우
            await self.session.rollback()
            existing = await self.inquiries.get_by_request_id(request.request_id)
            if existing is None:
                raise
            return self._replay(existing, request)
        return _response(inquiry)

    async def _chat(self, request: InquiryRequest, token: str | None) -> Chat | None:
        if request.chat_id is None:
            if request.trigger_turn_id is not None:
                raise _invalid("대화 없이 답변을 연결할 수 없어요.", "chat_id")
            return None
        return await authorize_chat(self.chats, request.chat_id, token)

    @staticmethod
    def _replay(existing: Inquiry, request: InquiryRequest) -> InquiryResponse:
        if not _same_request(existing, request):
            raise AppError(ErrorCode.CONFLICT)
        return _response(existing)

    async def _check_links(self, request: InquiryRequest, chat: Chat | None) -> None:
        if request.origin == "agent_request" and chat is None:
            raise _invalid("상담사 연결은 대화가 필요해요.", "chat_id")

        trigger = None
        if request.trigger_turn_id is not None:
            trigger = await self.chats.get_turn(request.trigger_turn_id)
            if (
                trigger is None
                or chat is None
                or trigger.chat_id != chat.id
                or trigger.status != "completed"
            ):
                raise _invalid("연결할 답변을 이 대화에서 찾을 수 없어요.", "trigger_turn_id")

        if request.origin == "uncertain_answer_card" and (
            trigger is None or not trigger.show_contact
        ):
            raise _invalid("문의 카드가 뜬 답변을 함께 보내 주세요.", "trigger_turn_id")

        # 대화가 시작된 상태(완료 turn이 있음)면 origin과 상관없이 trigger가 있어야 연결 문의로 보인다
        if chat is not None and trigger is None and await self.chats.has_completed_turn(chat.id):
            raise _invalid("대화 중 문의는 마지막 답변을 함께 보내 주세요.", "trigger_turn_id")
