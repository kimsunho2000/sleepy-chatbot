"""관리자 로그인과 토큰 확인."""

from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.core.security import issue_admin_token
from tests.conftest import ADMIN_PASSWORD


async def login(client: AsyncClient, password: str = ADMIN_PASSWORD) -> tuple[int, dict, dict]:
    response = await client.post(
        "/api/admin/tokens", json={"username": "admin", "password": password}
    )
    return response.status_code, response.json(), dict(response.headers)


async def test_login_and_current_token(client: AsyncClient) -> None:
    status, body, _ = await login(client)
    assert status == 201
    assert body["display_name"] == "테스트 관리자"

    current = await client.get(
        "/api/admin/tokens/current", headers={"Authorization": f"Bearer {body['token']}"}
    )
    assert current.status_code == 200
    assert current.json()["display_name"] == "테스트 관리자"


async def test_wrong_password_is_401_without_reason(client: AsyncClient) -> None:
    status, body, _ = await login(client, "wrong")
    assert status == 401
    assert body["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("settings_overrides", [{"admin_login_max_failures": 3}])
async def test_repeated_failures_lock_ip(client: AsyncClient) -> None:
    for _ in range(3):
        assert (await login(client, "wrong"))[0] == 401
    # 차단 중에는 맞는 비밀번호도 막는다
    status, body, headers = await login(client)
    assert status == 429
    assert body["error"]["code"] == "rate_limited"
    assert int(headers["retry-after"]) > 0


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Bearer not-a-jwt",
        "Bearer " + issue_admin_token("admin", "x", "u" * 32, timedelta(hours=1))[0],
        "Bearer " + issue_admin_token("admin", "x", "t" * 32, timedelta(hours=-1))[0],
        "Bearer " + issue_admin_token("someone", "x", "t" * 32, timedelta(hours=1))[0],
    ],
    ids=["missing", "garbage", "other-secret", "expired", "other-user"],
)
async def test_current_token_rejects_invalid(
    client: AsyncClient, authorization: str | None
) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    response = await client.get("/api/admin/tokens/current", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
