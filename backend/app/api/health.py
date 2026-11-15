"""서버 상태 확인. 배포 후 서버가 떴는지 보는 용도다.

DB 마이그레이션과 RAG 인덱스 확인은 서버 시작 단계에서 끝나므로(실패하면 서버가 뜨지 않는다)
여기서는 외부 서비스를 다시 부르지 않는다. 호출마다 OpenAI·DB 비용이 들지 않게 하기 위해서다.
"""

from fastapi import APIRouter

from app.schemas.health import HealthResponse

router = APIRouter(prefix="/health", tags=["상태 확인"])


@router.get("", response_model=HealthResponse, summary="서버 상태 확인")
async def get_health() -> HealthResponse:
    return HealthResponse()
