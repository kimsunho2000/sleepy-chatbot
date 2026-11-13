"""문의 저장소."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Inquiry


class InquiryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_request_id(self, request_id: uuid.UUID) -> Inquiry | None:
        return await self.session.scalar(select(Inquiry).where(Inquiry.request_id == request_id))

    async def add(self, inquiry: Inquiry) -> Inquiry:
        """저장하고 DB 시퀀스로 채번한 reference_no를 함께 돌려받는다."""
        self.session.add(inquiry)
        await self.session.flush()
        return inquiry
