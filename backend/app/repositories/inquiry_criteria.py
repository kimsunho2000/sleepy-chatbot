"""문의 집계 기준. 대시보드, 문의 목록 필터, 상단 배지가 같은 규칙을 쓰도록 한 곳에 둔다.

문의 관리 API(목록·건수)도 이 기준을 쓴다. 바꿀 때는 이 파일만 고친다.
"""

from sqlalchemy import ColumnElement

from app.db.models import Inquiry

# "처리 전" = 접수 + 처리 중 (ADMIN.md)
UNRESOLVED_INQUIRY_STATUSES: tuple[str, ...] = ("received", "in_progress")


def unresolved_inquiry() -> ColumnElement[bool]:
    return Inquiry.status.in_(UNRESOLVED_INQUIRY_STATUSES)


def unread_inquiry() -> ColumnElement[bool]:
    # 읽음 여부는 상태와 별개다. 한 번도 열어 보지 않은 문의는 상태와 상관없이 미확인이다
    return Inquiry.first_viewed_at.is_(None)
