# 슬리비 AI 고객상담 챗봇 (sleepy-chatbot)

(주)슬리피의 디지털 귀마개 **슬리비(Sleeby)** 홈페이지에 들어가는 **AI 고객상담 챗봇**입니다.
제품 자료와 FAQ에서 찾은 내용만을 근거로 답하고, 답하기 어려운 문의는 담당자 문의로 연결합니다.

> 상태: **개발 중** (챗봇 백엔드 API, 챗봇 화면, 관리자 화면이 구현되어 있고 배포를 준비하는 단계)

## 소개

- **해결하려는 문제:** 고객이 제품 특징, 사용 방법, 유의사항, 구매 방법을 물을 때 담당자가 매번 답하지 않아도 되게 하고, AI가 자료에 없는 내용을 지어내지 않게 합니다.
- **주요 사용자:** 슬리비 홈페이지를 찾는 고객(챗봇 사용), 문의를 확인하는 담당자(관리자 화면 사용).
- **RAG란?** 질문과 관련된 자료를 먼저 검색(Retrieval)하고, 찾은 자료를 근거로 답변을 생성(Generation)하는 방식입니다.

## 데모 화면

> 시연 화면입니다. 표시된 문의와 수치는 예시 데이터이며 실제 고객 데이터가 아닙니다.

**홈페이지와 챗봇 위젯**: 분야를 고르거나 추천 질문을 눌러 바로 물어볼 수 있습니다.

![홈페이지와 챗봇 위젯](assets/screenshots/demo-home-widget.jpg)

**답변과 담당자 문의 접수(모바일)**: 답변 아래 "담당자에게 문의 남기기"를 누르고, 이름·이메일·내용을 입력하면 접수 번호를 안내합니다. 문의에는 지금까지의 대화가 함께 전달됩니다.

![답변과 담당자 문의 접수 3단계](assets/screenshots/demo-inquiry-flow.jpg)

**관리자 대시보드**: 질문 수, 평균 응답 시간, 답변 유형, 고객 평가, 많이 참고된 FAQ, 예상 AI 비용을 한 화면에서 봅니다.

![관리자 대시보드](assets/screenshots/demo-admin-dashboard.jpg)

## 주요 기능

**구현됨**

- **근거 기반 답변:** 검색된 FAQ·제품 정보에 적힌 내용으로만 답하고, 추측하지 않습니다.
- **담당자 문의 연결:** 근거가 없거나 불확실하면 문의 카드를 띄웁니다. 상담사 연결 버튼과 직접 문의 폼도 있습니다.
- **범위 안내:** 제품과 관련 없는 질문에는 답변 범위를 안내합니다.
- **의료 효과 단정 금지:** 슬리비는 질환을 진단·치료하는 제품이 아닙니다. 효과를 단정하거나 보장하지 않습니다.
- **답변 평가:** 고객이 답변마다 👍/👎(틀림·부족함·질문과 무관)를 남길 수 있습니다.
- **관리자 화면과 API:** 문의 관리, 질문 로그, 답 못 한 질문 묶음, 대시보드를 관리자 화면(`admin/`)과 API로 제공합니다.

고객 응답에는 출처를 넣지 않습니다. 검색 후보, 답변 근거, 판단 사유는 관리자 API에서만 볼 수 있습니다.

**예정 (설계 문서 기준)**: 답변 스트리밍·멈추기, 새로고침 후 대화 복원.

## 기술 스택

| 영역 | 기술 | 역할 |
|---|---|---|
| 프론트엔드 | React 19, Vite (JavaScript) | 챗봇 화면, 소개 페이지(`frontend/`), 관리자 화면(`admin/`) |
| 백엔드 | FastAPI, SQLAlchemy(asyncio), Alembic (Python 3.11+, 패키지 관리 `uv`) | 고객·관리자 API |
| RAG | LangChain, Qdrant(로컬 모드 또는 Qdrant Cloud) | 임베딩 + 키워드 검색, 답변 판단과 생성 |
| 모델 | OpenAI Embeddings, OpenAI GPT | 모델 이름은 [`configs/rag/default.yaml`](configs/rag/default.yaml)에 명시 |
| 업무 DB | PostgreSQL | 대화·문의·로그 저장 (운영 Supabase, 로컬 Docker) |
| 배포 | 백엔드: 루트 [`Dockerfile`](Dockerfile)(Cloud Run 배포 예시 포함), 프론트엔드·관리자 화면: Vercel | 서비스 배포 |

버전 기준은 [`backend/pyproject.toml`](backend/pyproject.toml)과 [`frontend/package.json`](frontend/package.json)입니다.

## 시작하기

**사전 요구사항:** Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js, Docker(로컬 DB), OpenAI API 키.
명령은 하나씩 실행하세요(Windows PowerShell 5.1에서는 `&&`가 동작하지 않습니다).

### 빠른 실행 요약

처음 한 번만 아래 1~3단계(복제, 환경변수, 백엔드 준비)를 마치면, 이후에는 터미널 세 개에서 다음 명령만 실행합니다.

| 터미널 | 위치 | 명령 | 열리는 주소 |
|---|---|---|---|
| 백엔드 | `backend/` | `uv run uvicorn app.main:create_app --factory --reload` | http://localhost:8000 (`/docs`, `/health`) |
| 챗봇 화면 | `frontend/` | `npm run dev` | http://localhost:5173 |
| 관리자 화면 | `admin/` | `npm run dev` | http://localhost:5175 |

DB가 꺼져 있으면 `backend/`에서 `docker compose up -d`를 먼저 실행합니다. 두 화면이 백엔드를 부르려면 `.env`의 `CORS_ORIGINS`에 위 두 화면 주소(`http://localhost:5173`, `http://localhost:5175`)가 들어 있어야 합니다. `.env.example`의 기본값 그대로면 됩니다.

### 1. 저장소 복제

```bash
git clone https://github.com/sleepy-team/sleepy-chatbot.git
cd sleepy-chatbot
```

### 2. 환경변수

저장소 루트에 `.env`를 만들고 [`.env.example`](.env.example)을 참고해 채웁니다. `.env`는 커밋하지 않습니다.

| 변수 | 설명 |
|---|---|
| `OPENAI_API_KEY` | OpenAI API 키 |
| `QDRANT_URL`, `QDRANT_API_KEY` | Qdrant Cloud 주소와 키. 비우면 로컬 모드(`.qdrant/`)를 씁니다 |
| `DATABASE_URL` | PostgreSQL 연결 문자열. 로컬 Docker: `postgresql://sleeby:sleeby@localhost:5433/sleeby` |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | 관리자 계정 1개 |
| `ADMIN_DISPLAY_NAME` | 관리자 화면에 보이는 이름 (기본값 `관리자`) |
| `ADMIN_TOKEN_SECRET` | 관리자 토큰 서명 비밀값 (32자 이상) |
| `IP_HASH_SECRET` | 클라이언트 IP 해시용 비밀값 (16자 이상) |
| `CORS_ORIGINS` | 허용할 프론트 도메인(JSON 배열). 비우면 브라우저 호출이 모두 막힙니다 |
| `TRUSTED_PROXY_COUNT` | 앞단 프록시 수. 0이면 `X-Forwarded-For`를 무시합니다 |

> [!NOTE]
> 연결 문자열에 `sslmode=...`를 붙이지 마세요. 백엔드가 쓰는 asyncpg 드라이버는 `ssl=...`만 받습니다.

### 3. 백엔드

```bash
cd backend
uv sync
docker compose up -d
uv run alembic upgrade head
```

RAG 검색 색인을 한 번 만듭니다. OpenAI 임베딩 호출 비용이 듭니다.

```bash
uv run python -m rag.indexer --config configs/rag/default.yaml
```

서버를 실행합니다.

```bash
uv run uvicorn app.main:create_app --factory --reload
```

### 4. 프론트엔드

```bash
cd frontend
npm install
npm run dev
```

Vite 기본 주소는 http://localhost:5173 입니다. 백엔드 주소는 환경변수 `VITE_API_BASE_URL`로 바꿉니다(기본값 `http://localhost:8000`).
백엔드 없이 화면만 보려면 브라우저 안의 간단한 엔진으로 동작하는 데모 모드를 씁니다.

```bash
npm run demo
```

### 5. 관리자 화면 (선택)

```bash
cd admin
npm install
npm run dev
```

http://localhost:5175 에서 열립니다. 백엔드 없이 명세 모양의 가짜 데이터로 보려면 `npm run mock`을 씁니다. 로그인은 `.env`의 `ADMIN_USERNAME`, `ADMIN_PASSWORD`를 씁니다. 개발 서버가 아닌 빌드에서는 `VITE_API_BASE_URL`을 꼭 지정해야 합니다(없으면 "API 주소가 설정되지 않았어요" 오류).

### 6. 정상 실행 확인

- 브라우저에서 http://localhost:8000/docs 에 API 문서(Swagger)가 열립니다.
- http://localhost:8000/health 가 `{"status": "ok"}`를 돌려주면 서버가 떠 있는 것입니다. DB·OpenAI는 다시 부르지 않습니다.
- 새 대화가 만들어지면(`201`) DB와 연결된 것입니다.

```bash
curl -X POST http://localhost:8000/api/chats
```

### 종료와 다시 시작

- 각 터미널에서 `Ctrl+C`로 서버를 멈춥니다.
- 로컬 DB는 `backend/`에서 `docker compose down`으로 멈춥니다(데이터는 Docker 볼륨에 남습니다).
- 다시 시작할 때는 위 "빠른 실행 요약"의 명령만 다시 실행하면 됩니다. 색인은 FAQ 데이터나 임베딩 모델이 바뀔 때만 다시 만듭니다.

### 막혔을 때 확인할 것

| 증상 | 확인할 것 |
|---|---|
| 서버 시작 시 `IndexOutdatedError`("인덱서를 다시 실행하세요") | 색인이 없거나 데이터·임베딩 모델과 맞지 않습니다. `uv run python -m rag.indexer --config configs/rag/default.yaml`을 다시 실행합니다 |
| 서버 시작 시 OpenAI `403`(모델 접근 권한 없음) | `configs/rag/default.yaml`에 적힌 모델을 OpenAI 프로젝트에서 쓸 수 있어야 합니다. 키의 프로젝트 권한을 확인합니다 |
| 화면에 "서버와 연결하지 못했어요" 또는 브라우저 콘솔의 CORS 오류 | 백엔드가 떠 있는지, `.env`의 `CORS_ORIGINS`에 화면 주소가 있는지 확인합니다. 값을 바꿨다면 백엔드를 다시 시작합니다 |
| DB 연결 오류 | `docker compose up -d`로 DB가 켜져 있는지, `DATABASE_URL`이 맞는지, 주소에 `sslmode`가 없는지 확인합니다 |
| 관리자 화면에서 "API 주소가 설정되지 않았어요" | 개발 서버(`npm run dev`)가 아닌 빌드에서는 `VITE_API_BASE_URL`을 지정해야 합니다 |

## 사용 방법

고객 한 명의 기본 흐름은 **대화 만들기 → 질문 → (평가) → (문의)** 입니다.

1. 대화를 만들면 `chat_id`와 `chat_token`을 한 번 받습니다. 이후 요청은 `Authorization: Bearer <chat_token>` 헤더가 필요합니다.
2. 질문을 보내면 답변 1건을 받습니다. 후속 질문은 직전 답변의 `turn_id`를 `parent_turn_id`로 보냅니다.
3. 답변에 `show_contact`가 `true`면 화면이 문의 카드를 띄웁니다.

```bash
curl -X POST http://localhost:8000/api/chats/<chat_id>/turns \
  -H "Authorization: Bearer <chat_token>" \
  -H "Content-Type: application/json" \
  -d '{"question": "충전은 얼마나 걸리나요?", "parent_turn_id": null}'
```

응답 예시(고객 응답에는 출처·판단 사유·토큰 정보가 없습니다):

```json
{
  "turn_id": "<uuid>",
  "chat_id": "<uuid>",
  "parent_turn_id": null,
  "question": "충전은 얼마나 걸리나요?",
  "mode": "answer",
  "answer": "<검색 근거로 생성된 답변>",
  "show_contact": false,
  "feedback": null,
  "created_at": "<UTC ISO 8601 시각>"
}
```

`mode`는 `answer`(답변), `partial`(일부만 답변), `unknown`(근거 없음), `offtopic`(범위 밖), `greeting`(인사) 중 하나입니다.
`unknown`은 오류가 아닌 정상 결과입니다. Windows PowerShell에서는 JSON 따옴표가 깨지기 쉬우니 위 `/docs` 화면에서 시험해 보는 것을 권합니다.

## 프로젝트 구조

```
sleepy-chatbot/
├── frontend/        # React 챗봇 UI
├── admin/           # React 관리자 화면
├── assets/          # README에 쓰는 데모 화면 이미지
├── backend/
│   ├── app/         # FastAPI: api/ services/ repositories/ schemas/ core/ db/
│   ├── rag/         # RAG 모듈 (prompts/ 에 시스템 프롬프트)
│   ├── migrations/  # Alembic 마이그레이션
│   └── tests/       # API 테스트
├── configs/rag/     # RAG 설정 파일 (채택: default.yaml)
├── data/            # 정리된 FAQ·제품 정보 JSON (RAG 인덱싱 대상)
├── eval/            # 개발용 평가 세트와 평가 스크립트
└── Dockerfile       # 백엔드 배포 이미지
```

아키텍처는 다음 순서로 흐릅니다.

```
React UI → API (FastAPI Router) → Service → RAG 모듈 → Qdrant
                                          → Repository → PostgreSQL
```

- Router는 요청·응답 검증만 하고 Service를 호출합니다.
- Service는 대화 흐름, 요청 제한, 답변 불가 시 문의 유도, 로그 기록을 맡습니다.
- RAG 모듈([`backend/rag/`](backend/rag/))은 FastAPI에 의존하지 않고, 설정 파일만 받아 단독으로 실행·평가할 수 있습니다.

## API

공개 명세: https://sleepy-team.github.io/sleepy-chatbot/ — 경로는 `/api`, JSON은 snake_case, 시간은 UTC ISO 8601입니다.
오류는 `{"error": {"code", "message", "fields"}}` 형식이고, 요청 제한에 걸리면 `Retry-After` 헤더로 남은 초를 줍니다.

| 구분 | 엔드포인트 |
|---|---|
| 고객 챗봇 | `POST /chats`, `POST /chats/{chat_id}/turns`, `PUT·DELETE /chats/{chat_id}/turns/{turn_id}/feedback`, `POST /inquiries` |
| 상태 확인 | `GET /health` (경로에 `/api`가 붙지 않음) |
| 관리자 접근 | `POST /admin/tokens`, `GET /admin/tokens/current` |
| 관리자 문의 | `GET /admin/inquiries`, `GET /admin/inquiry-counts`, `GET·PATCH /admin/inquiries/{id}` |
| 질문 로그 | `GET /admin/turns`, `GET /admin/turns/{id}` |
| 답 못 한 질문 | `GET /admin/unanswered-groups`, `GET /admin/unanswered-groups/{group_key}` |
| 대시보드 | `GET /admin/dashboard` |

인증은 `Authorization: Bearer <토큰>` 하나입니다. 고객은 대화를 만들 때 한 번 받는 대화 토큰을, 관리자는 로그인으로 받는 관리자 토큰을 씁니다.
관리자 로그인은 같은 IP에서 연속 5회 실패하면 15분간 차단됩니다.

## RAG 설정

- 채택 설정은 [`configs/rag/default.yaml`](configs/rag/default.yaml)입니다. 임베딩·LLM 모델, 검색 방식, 판단 기준이 이 파일에 있습니다.
- 말투와 세부 응답 규칙은 코드가 아니라 [`backend/rag/prompts/default.yaml`](backend/rag/prompts/default.yaml)에서 관리합니다.
- 이미 결과를 낸 설정 파일은 덮어쓰지 않고, 새 실험은 새 설정 파일로 만듭니다.
- 데이터([`data/faq.json`](data/faq.json), [`data/product.json`](data/product.json))는 팀이 공유한 원본 그대로 쓰며, 각자 수정하지 않습니다.

## 테스트와 검증

백엔드 테스트는 별도 DB(`sleeby_test`)를 쓰고, 실제 OpenAI를 부르지 않는 가짜 RAG를 넣습니다.

> [!WARNING]
> 테스트는 `sleeby_test` DB의 표를 비우고 시작합니다. 운영 DB 주소를 넣지 마세요.

```bash
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

```bash
cd frontend
npm run lint
npm run format:check
npm run build
```

**검증된 항목 (2026-11-14, 로컬 임시 PostgreSQL 기준)**

- 백엔드 테스트 174개와 `ruff` 검사 통과.
- 프론트엔드 `lint`와 `build` 통과 (관리자 화면 이전 시점). `format:check`는 이때 13개 파일에서 실패했습니다.
- 브라우저에서 챗봇 화면과 백엔드 연동: 대화 생성, 질문, 답변 평가, 상담사 연결 문의 접수.
- ERD·API 설계 문서와의 대조: 테이블, 제약, 인덱스, 16개 API의 응답 형식.

**답변 품질 평가 (2026-11-15, 채택 설정, 실제 OpenAI 호출)**

- 개발 세트 39문항과 위험·돌발 19문항을 3번씩 물어 답변 174개를 점검했습니다. 근거 없는 답변 0건, 자료에 없거나 범위 밖인 질문 42번 모두 보류했습니다.
- 자세한 결과와 남은 문제: [답변 품질 평가 리포트](<eval/슬리비 FAQ AI 챗봇 답변 품질 평가 리포트.md>)

**검증하지 못한 항목**

- 운영 Supabase(6543 포트 pooler) 연결과 배포 환경 동작.
- 팀 평가 세트 기반 평가(비공개 자료라 저장소에 없음).
- 관리자 화면과 실제 백엔드의 연동, 모바일 화면.

## 개발 현황과 알려진 제약

- **구현 완료:** 고객 챗봇 API, 문의 접수 API, 관리자 API(문의·질문 로그·답 못 한 질문·대시보드), 챗봇 화면, 관리자 화면, 서버 상태 확인 API, 백엔드 배포 이미지(Dockerfile).
- **개발 중:** 팀 검증 결과에 따른 RAG 개선, 실제 배포.
- **알려진 제약 (2026-11-15 답변 품질 평가 기준)**
  - 자해 암시나 응급 증상 같은 위기 표현에 대한 전용 안내가 아직 없습니다. 자해 암시 질문은 3번 모두 도움 안내 없이 범위 밖 안내 등으로 처리됐습니다.
  - FAQ에 답이 있는데도 보류하는 경우가 있습니다(답해야 하는 질문의 10~15%).
  - 외국어 질문에 그 언어로 답하는 규칙이 있지만, 영어 복합 질문은 3번 중 1번만 영어로 답했습니다. 일본어 질문은 3번 모두 일본어로 답했습니다.
  - 같은 질문의 판단이 실행마다 달라질 수 있습니다(LLM 특성). 개발 세트 39문항 중 5문항은 실행마다 판단이 달랐습니다.
  - `DATABASE_URL`의 `sslmode` 쿼리는 지원하지 않습니다.

## 협업

- 브랜치는 `main`에서 `type/작업내용`으로 만들고, Pull Request로만 `main`에 반영합니다. `main`에 직접 커밋·push하지 않습니다.
- 커밋은 Conventional Commits(`type(scope): 요약`)를 따릅니다.
- 코드 스타일, 커밋·PR 작성법은 팀에 공유된 `CONVENTION.md`를 따릅니다(저장소에 포함되지 않는 팀 공유 파일).

## 보안과 자료 관리

- API 키, 비밀번호, 토큰은 저장소에 커밋하지 않습니다. `.env`는 Git 관리 대상에서 제외합니다.
- 원본 IP는 저장하지 않고, 서버 비밀값으로 만든 해시만 저장합니다.
- 기업 제공 자료(`docs/`)는 저장소에 포함하지 않습니다. 이용·공유 권한을 확인한 뒤 취급합니다.
- 비공개 최종 평가 질문과 정답은 저장소에 두지 않습니다.
- 실제 고객 데이터는 사용하지 않고 데모 데이터만 씁니다.
- 모델 학습·파인튜닝, 상담원 배정·티켓 시스템, 상용 수준의 인증·보안은 범위에 포함하지 않습니다.
