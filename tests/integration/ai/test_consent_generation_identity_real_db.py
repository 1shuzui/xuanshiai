"""Real MySQL regression coverage for consent generation identity.

Run serially with the AI integration suite; never share the test owner because
its fixtures intentionally clean data for that owner.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai.memory.projections import MemoryProjectionService
from app.services.ai.profile import PROFILE_POLICY_REVISION
from tests.integration.ai.test_ai_memory_projection_real_db import (
    _clean_owner,
    _grant_consent,
    _grant_search_dimension,
    _seed_confirmed_claim,
    _service,
)

pytestmark = pytest.mark.asyncio
OWNER_ID = 9_876_543_891


async def test_same_second_regrant_invalidates_old_projection_and_rebuilds(
    real_db_session: AsyncSession,
) -> None:
    db = real_db_session
    await _clean_owner(db, OWNER_ID)
    await db.execute(
        text("DELETE FROM ai_consent_grant WHERE user_id = :owner"),
        {"owner": OWNER_ID},
    )
    await _grant_consent(db, OWNER_ID, f"generation-{OWNER_ID}-first")
    await _seed_confirmed_claim(db, OWNER_ID, "generation", "喜欢散步")
    await _grant_search_dimension(db, OWNER_ID)
    service = _service(db)
    old = await service.build(
        owner_user_id=OWNER_ID,
        function_key="search",
        purpose="candidate_filter",
        data_category="personal_profile",
    )
    first_consent = await service._load_active_consent(OWNER_ID)
    assert first_consent is not None

    # Simulate revoke + regrant within one DATETIME second, using the same
    # durable table and timestamp; only the AUTO_INCREMENT id changes.
    await db.execute(
        text(
            "UPDATE ai_consent_grant SET revoked_at = UTC_TIMESTAMP(), user_id = NULL "
            "WHERE id = :grant_id"
        ),
        {"grant_id": int(first_consent["grant_id"])},
    )
    await db.execute(
        text(
            "INSERT INTO ai_consent_grant "
            "(user_id, scope, version, policy_revision, granted_at) "
            "VALUES (:owner, :scope, :version, :policy, :granted_at)"
        ),
        {
            "owner": OWNER_ID,
            "scope": "profile_text_extract",
            "version": first_consent["version"],
            "policy": PROFILE_POLICY_REVISION,
            "granted_at": first_consent["granted_at"],
        },
    )
    new_consent = await service._load_active_consent(OWNER_ID)
    assert new_consent is not None
    assert int(new_consent["grant_id"]) != int(first_consent["grant_id"])
    assert new_consent["granted_at"] == first_consent["granted_at"]
    assert MemoryProjectionService._snapshot_id(new_consent) != old["consent_snapshot_id"]
    assert await service.read_active(
        owner_user_id=OWNER_ID,
        function_key="search",
        purpose="candidate_filter",
        data_category="personal_profile",
    ) is None

    await _grant_search_dimension(db, OWNER_ID)
    rebuilt = await service.build(
        owner_user_id=OWNER_ID,
        function_key="search",
        purpose="candidate_filter",
        data_category="personal_profile",
    )
    assert rebuilt["projection_version"] > old["projection_version"]
    assert rebuilt["consent_snapshot_id"] == MemoryProjectionService._snapshot_id(new_consent)
    assert await service.read_active(
        owner_user_id=OWNER_ID,
        function_key="search",
        purpose="candidate_filter",
        data_category="personal_profile",
    ) is not None
    await db.commit()
