import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from app.api.dependencies import CurrentUser
from app.services import parent
from app.schemas.parent import ParentConsentAccept, ParentChildUpdate


class Rows:
    def __init__(self, row): self.row = row
    def mappings(self): return self
    def first(self): return self.row
    def scalar(self): return 1 if self.row else None


class RelationshipStore:
    def __init__(self, status="granted", child_id=202, expiry=None):
        self.row = {"parent_id": 101, "child_id": child_id, "status": status,
                    "expires_at": expiry or datetime.now(UTC) + timedelta(days=1),
                    "consent_version": parent.CONSENT_VERSION, "parent_status": 1,
                    "parent_realname_status": 2, "child_status": 1, "child_realname_status": 2}
    async def execute(self, statement, params=None): return Rows(self.row)


def actor(user_id=101):
    return CurrentUser(id=user_id, session_id=1, phone="test", status=1, realname_status=2)


def test_parent_subject_is_resolved_from_live_relationship():
    relation = asyncio.run(parent.authorize_parent(RelationshipStore(), actor(), 202))
    assert relation["child_id"] == 202
    with pytest.raises(HTTPException) as error:
        asyncio.run(parent.authorize_parent(RelationshipStore(), actor(), 999))
    assert error.value.status_code == 403


@pytest.mark.parametrize("status,expiry", [
    ("pending", None), ("revoked", None),
    ("granted", datetime.now(UTC) - timedelta(seconds=1)),
])
def test_old_context_cannot_bypass_revocation_or_expiry(status, expiry):
    with pytest.raises(HTTPException) as error:
        asyncio.run(parent.authorize_parent(RelationshipStore(status, expiry=expiry), actor(), 202))
    assert error.value.status_code == 403


def test_parent_and_child_must_both_remain_eligible():
    for field, value in [("parent_status", 2), ("child_status", 2),
                         ("parent_realname_status", 0), ("child_realname_status", 0)]:
        store = RelationshipStore()
        store.row[field] = value
        with pytest.raises(HTTPException):
            asyncio.run(parent.authorize_parent(store, actor(), 202))


def test_consent_requires_explicit_current_policy_and_bounded_duration():
    from pydantic import ValidationError
    for payload in [{"code": "x" * 32, "confirmed": False},
                    {"code": "x" * 32, "confirmed": 1},
                    {"code": "x" * 32, "confirmed": "true"},
                    {"code": "x" * 32, "confirmed": True, "days": 365},
                    {"code": "x" * 32, "confirmed": True, "consentVersion": "unknown"}]:
        with pytest.raises(ValidationError): ParentConsentAccept.model_validate(payload)


def test_parent_idempotency_namespace_is_bounded_and_actor_specific():
    from app.api.routes.parent import _command_key
    assert len(_command_key(101, "x" * 128)) <= 128
    assert _command_key(101, "x") != _command_key(102, "x")
    assert _command_key(101, "x") == _command_key(101, "x")


def test_parent_profile_rejects_nonadult_or_fractional_birth_year():
    from pydantic import ValidationError
    for year in [2020, 1990.5]:
        with pytest.raises(ValidationError):
            ParentChildUpdate(displayName="测试", birthYear=year, city="南京", job="", introduction="")


def test_parent_privacy_projection_removes_media_and_nested_contacts():
    payload = {"list": [{"avatar": "private.jpg", "clearAvatar": "private.jpg", "phone": "secret",
                         "nested": {"wechat": "secret"}, "content": "private.jpg", "type": "image"}]}
    result = parent.protect_parent_payload(payload)
    assert "private.jpg" not in str(result)
    assert "secret" not in str(result)
    assert result["list"][0]["content"] == ""
