"""관리자 접근(로그인 토큰) API 스키마."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Annotated[str, Field(min_length=1, max_length=100)]
    password: Annotated[SecretStr, Field(min_length=1, max_length=200)]


class TokenResponse(BaseModel):
    token: str
    display_name: str
    expires_at: datetime


class AdminIdentity(BaseModel):
    display_name: str
    expires_at: datetime
