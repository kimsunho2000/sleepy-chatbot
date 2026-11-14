"""고객 챗봇: 대화 생성, 질문, 피드백."""

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import ChatServiceDep, ChatTokenDep, ClientIpHashDep
from app.schemas.chat import (
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
    TurnRequest,
    TurnResponse,
)
from app.schemas.error import error_responses

router = APIRouter(prefix="/api/chats", tags=["고객 챗봇"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatResponse,
    responses=error_responses(422, 429, 503),
    summary="새 대화 (대화 초기화도 새 대화를 만든다)",
)
async def create_chat(service: ChatServiceDep, ip_hash: ClientIpHashDep) -> ChatResponse:
    created = await service.create_chat(ip_hash)
    return ChatResponse(
        chat_id=created.chat.id, chat_token=created.token, created_at=created.chat.created_at
    )


@router.post(
    "/{chat_id}/turns",
    status_code=status.HTTP_201_CREATED,
    response_model=TurnResponse,
    responses=error_responses(401, 404, 422, 429, 503, 504),
    summary="질문 1건, 답변 1건",
)
async def create_turn(
    chat_id: uuid.UUID,
    body: TurnRequest,
    service: ChatServiceDep,
    token: ChatTokenDep,
    ip_hash: ClientIpHashDep,
) -> TurnResponse:
    chat = await service.authorize(chat_id, token)
    return await service.ask(chat, body, ip_hash)


@router.put(
    "/{chat_id}/turns/{turn_id}/feedback",
    response_model=FeedbackResponse,
    responses=error_responses(401, 404, 422, 503),
    summary="👍/👎 등록·교체",
)
async def put_feedback(
    chat_id: uuid.UUID,
    turn_id: uuid.UUID,
    body: FeedbackRequest,
    service: ChatServiceDep,
    token: ChatTokenDep,
) -> FeedbackResponse:
    chat = await service.authorize(chat_id, token)
    return await service.put_feedback(chat, turn_id, body)


@router.delete(
    "/{chat_id}/turns/{turn_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(401, 404, 422, 503),
    summary="피드백 취소",
)
async def delete_feedback(
    chat_id: uuid.UUID, turn_id: uuid.UUID, service: ChatServiceDep, token: ChatTokenDep
) -> Response:
    chat = await service.authorize(chat_id, token)
    await service.delete_feedback(chat, turn_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
