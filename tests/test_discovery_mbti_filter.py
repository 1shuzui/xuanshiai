"""MBTI 筛选维度（2026-11-02，Q19）。

此前 ``/discovery/filter-options`` 不含 MBTI、``DiscoveryFilters`` 也没有该字段，
前端只能硬编码「MBTI 筛选未开放」。本文件锁定：

1. ``filters.mbti`` 走 16 型枚举校验，非法值 422；
2. SQL 用**参数化 IN**，不拼接用户输入；
3. 空列表等价于不筛选（与项目「空串不筛选」的既有约定一致）；
4. 选项接口真的下发 16 型。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_browsable_user
from app.api.routes import discovery
from app.db.session import get_db
from app.schemas.discovery import DiscoveryFilters, DiscoveryPage
from app.services.discovery import _filter_sql, get_filter_options


def test_mbti_filter_builds_parameterized_in_clause() -> None:
    params: dict[str, object] = {}
    clauses = _filter_sql(DiscoveryFilters(mbti=["INTJ", "ENFP"]), params)

    assert clauses == ["p.mbti IN (:filter_mbti_0, :filter_mbti_1)"]
    assert params == {"filter_mbti_0": "INTJ", "filter_mbti_1": "ENFP"}


def test_mbti_empty_list_is_noop() -> None:
    params: dict[str, object] = {}
    assert _filter_sql(DiscoveryFilters(mbti=[]), params) == []
    assert params == {}


def test_mbti_absent_is_noop() -> None:
    params: dict[str, object] = {}
    assert _filter_sql(DiscoveryFilters(), params) == []


@pytest.mark.parametrize("bad", ["XXXX", "intj", "INTJX", ""])
def test_invalid_mbti_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        DiscoveryFilters(mbti=[bad])


def test_mbti_list_length_capped() -> None:
    # 16 型去重后最多 16 个，超出直接拒绝，避免构造超长 IN 列表。
    with pytest.raises(ValidationError):
        DiscoveryFilters(mbti=["INTJ"] * 17)


@pytest.mark.asyncio
async def test_filter_options_expose_all_16_types() -> None:
    options = await get_filter_options()
    values = [item["value"] for item in options.mbti_types]
    assert len(values) == 16
    assert len(set(values)) == 16
    assert "INTJ" in values
    assert all(item["label"] for item in options.mbti_types)


@pytest.mark.parametrize("endpoint", ["recommendations", "plaza"])
def test_discovery_mbti_is_a_repeated_query_parameter(
    monkeypatch: pytest.MonkeyPatch, endpoint: str,
) -> None:
    app = FastAPI()
    app.include_router(discovery.router)
    app.dependency_overrides[get_browsable_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_db] = object
    service = AsyncMock(
        return_value=DiscoveryPage(items=[], page=1, page_size=20, total=0, has_more=False)
    )
    monkeypatch.setattr(discovery, "get_discovery_page", service)
    client = TestClient(app)
    url = f"/discovery/{endpoint}"

    response = client.get(
        url,
        params=[
            ("mbti", "INTJ"), ("mbti", "ENFP"), ("age_min", "25"),
            ("gender", "1"), ("marriage_status", "3"),
        ],
    )

    assert response.status_code == 200, response.text
    filters = service.await_args.args[2]
    assert filters.mbti == ["INTJ", "ENFP"]
    assert filters.age_min == 25
    assert filters.gender == 1
    assert filters.marriage_status == 3
    assert service.await_args.kwargs["plaza"] == (endpoint == "plaza")

    assert client.get(url, params={"mbti": "unknown"}).status_code == 422
    assert client.get(url, params={"gender": "3"}).status_code == 422
    assert service.await_count == 1
