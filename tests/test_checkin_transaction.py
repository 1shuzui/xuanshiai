from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import points


@pytest.mark.asyncio
async def test_daily_checkin_reuses_request_transaction_and_credits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = None

    async def execute(statement, params):
        nonlocal stored
        sql = str(statement)
        if "SELECT id,points FROM user_checkin" in sql:
            return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: stored))
        assert "INSERT INTO user_checkin" in sql
        stored = params

    credit = AsyncMock(return_value=108)
    monkeypatch.setattr(points, "_credit", credit)
    monkeypatch.setattr(points, "_balance", AsyncMock(return_value=108))
    monkeypatch.setattr(points.settings, "point_checkin_reward", 8)

    async with AsyncSession() as db:
        monkeypatch.setattr(db, "execute", execute)
        await db.begin()
        first = await points.checkin(db, 11)
        assert not db.in_transaction()
        await db.begin()
        repeated = await points.checkin(db, 11)
        assert not db.in_transaction()
        credit.assert_awaited_once_with(db, 11, 8, 1, "每日签到")

    assert first == repeated
    assert first.checked_in and first.balance == 108 and first.points == 8
