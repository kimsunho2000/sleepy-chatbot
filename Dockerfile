# 백엔드(FastAPI + RAG) 배포 이미지. 프론트·관리자 화면은 Vercel에 따로 올린다.
# RAG가 저장소 루트의 configs/·data/를 읽으므로 빌드 컨텍스트는 저장소 루트다.
#   Cloud Run: gcloud run deploy sleeby-backend --source . --region asia-northeast3
#   로컬:      docker build -t sleeby-backend .
# 비밀값(.env)은 이미지에 넣지 않는다. 실행 환경의 환경변수로 넘긴다.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/backend

# 의존성 층을 코드와 분리해, 코드만 바뀌면 설치를 다시 하지 않게 한다
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY configs/ /app/configs/
COPY data/ /app/data/

RUN useradd --create-home --uid 10001 app
USER app

ENV PATH="/app/backend/.venv/bin:$PATH"

# Cloud Run은 PORT 환경변수로 포트를 알려 준다.
# 인스턴스를 1개로 두므로 시작할 때 마이그레이션을 적용해도 서로 겹치지 않는다
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
