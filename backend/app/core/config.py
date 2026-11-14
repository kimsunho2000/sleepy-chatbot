"""서버 설정. 값은 저장소 루트 .env와 환경변수에서 읽는다."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from rag.config import REPO_ROOT


class DatabaseSettings(BaseSettings):
    """DB 연결만 필요한 곳(Alembic 마이그레이션)에서도 쓴다."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Supabase나 로컬 PostgreSQL 연결 문자열. postgresql:// 로 적어도 asyncpg 드라이버로 바꿔 쓴다
    database_url: str
    # Supabase transaction pooler(6543 포트)는 prepared statement를 유지하지 못한다.
    # None이면 포트 번호로 판단한다
    database_pgbouncer: bool | None = None

    @field_validator("database_url")
    @classmethod
    def use_asyncpg(cls, value: str) -> str:
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value.removeprefix(prefix)
        return value

    @property
    def uses_pgbouncer(self) -> bool:
        if self.database_pgbouncer is not None:
            return self.database_pgbouncer
        return ":6543/" in self.database_url


class AppSettings(DatabaseSettings):
    rag_config: str = "configs/rag/default.yaml"
    # RAG 호출 전체(OpenAI 재시도 포함)에 거는 제한 시간
    rag_timeout_seconds: float = 30.0

    admin_username: str
    admin_password: SecretStr
    admin_display_name: str = "관리자"
    admin_token_secret: SecretStr = Field(min_length=32)
    admin_token_ttl_hours: float = 12.0
    admin_login_max_failures: int = 5
    admin_login_lockout_minutes: int = 15

    # 클라이언트 IP를 DB에 원본 대신 해시로 남길 때 쓰는 비밀값
    ip_hash_secret: SecretStr = Field(min_length=16)
    # 앞단 프록시 수. X-Forwarded-For의 맨 오른쪽에서 이 순번의 값을 고객 IP로 쓴다.
    # 0이면 X-Forwarded-For를 무시하고 접속 주소를 쓴다 (Cloud Run 직접 연결은 1)
    trusted_proxy_count: int = Field(default=0, ge=0)
    # CORS 허용 도메인 (챗봇 프론트, 관리자 프론트). .env에는 JSON 배열로 적는다
    cors_origins: list[str] = Field(default_factory=list)

    chat_create_per_ip_per_minute: int = 10
    chat_create_per_ip_per_day: int = 30
    turn_per_chat_per_minute: int = 10
    turn_per_ip_per_minute: int = 30
    turn_per_ip_per_day: int = 100
    turn_global_per_day: int = 2000
    inquiry_per_ip_per_hour: int = 5

    # 예상 비용 단가(USD, 100만 토큰당). 정하지 않으면 관리자 화면의 예상 비용이 null이다
    llm_input_price_per_1m_tokens: float | None = Field(default=None, ge=0)
    llm_output_price_per_1m_tokens: float | None = Field(default=None, ge=0)


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
