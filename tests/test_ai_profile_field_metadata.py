"""Draft reads, frozen PATCH replay and revision writes keep field metadata."""

from __future__ import annotations

import json

import pytest

from app.schemas.ai_profile import ProfileDraftFieldPatchRequest, ProfileFieldPatchAction
from app.services.ai.profile import (
    _draft_from_response_payload,
    _draft_response_payload,
    confirm_profile_draft,
    insert_immutable_profile_revision,
    load_owned_draft,
)
from tests.test_ai_profile_entries import _entry_row
from tests.test_ai_profile_publish import ProfileStore


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", ["personal", "ideal_partner"])
@pytest.mark.parametrize("dimension", ["lifestyle", None])
@pytest.mark.parametrize("replay", [False, True])
async def test_field_metadata_survives_read_confirm_replay_and_revision_insert(
    subject: str, dimension: str | None, replay: bool,
) -> None:
    store = ProfileStore()
    row = await store.seed_draft(subject=subject, revision=1)
    draft_id = row["draft_id"]
    structured = next(f for f in store.draft_fields if f["draft_id"] == draft_id)
    # Historical structured rows have no field_kind or dimension populated.
    if dimension is not None:
        structured["profile_dimension"] = dimension
    entry = _entry_row(draft_id, "entry_values_metadata", subject=subject)
    entry.update(profile_dimension=dimension, replaces_field_key="entry_values_previous")
    store.draft_fields.append(entry)
    expected = {
        "field_kind": "entry",
        "profile_dimension": dimension,
        "category": entry["category"],
        "content": entry["content"],
        "replaces_field_key": entry["replaces_field_key"],
    }

    loaded = await load_owned_draft(store.session, draft_id, 10)
    assert loaded.subject == subject
    assert all(f.profile_dimension == dimension for f in loaded.fields)
    field_reads = [sql for sql, _ in store.session.calls if "FROM ai_profile_draft_field" in sql]
    assert field_reads and all("profile_dimension" in sql.split("FROM")[0] for sql in field_reads)

    actions = [
        ProfileDraftFieldPatchRequest(
            field_key=f.field_key, action=ProfileFieldPatchAction.CONFIRM, expected_revision=1,
        )
        for f in loaded.fields
    ]
    first = await confirm_profile_draft(
        store.session, draft_id, 10, actions, expected_revision=1, idempotency_key="metadata-patch",
    )
    history = json.loads(store.drafts_by_id[draft_id]["last_operation_response_json"])
    response = history["operations"]["metadata-patch"]["response"]
    saved_entry = next(f for f in response["fields"] if f["field_key"] == entry["field_key"])
    assert {key: saved_entry[key] for key in expected} == expected

    draft = first
    if replay:
        # A later live edit must not replace the response frozen for this key.
        entry.update(profile_dimension="intimacy_pattern", content="later live edit")
        structured["profile_dimension"] = "intimacy_pattern"
        before_replay = len(store.session.calls)
        draft = await confirm_profile_draft(
            store.session, draft_id, 10, actions, expected_revision=1, idempotency_key="metadata-patch",
        )
        assert draft.fields == first.fields
        assert draft.revision == first.revision == 2
        assert not any(
            sql.startswith(("INSERT", "UPDATE", "DELETE"))
            for sql, _ in store.session.calls[before_replay:]
        )

    await insert_immutable_profile_revision(
        store.session, 10, draft, draft.fields,
        target="profile" if subject == "personal" else "preference",
    )
    writes = [(sql, params) for sql, params in store.session.calls
              if "INSERT INTO ai_profile_revision_field" in sql]
    assert len(writes) == 2
    for sql, params in writes:
        assert "profile_dimension" in sql and ":profile_dimension" in sql
        assert params["subject"] == subject
        assert params["profile_dimension"] == dimension
    entry_write = next(params for _, params in writes if params["field_kind"] == "entry")
    assert {key: entry_write[key] for key in expected} == expected
    assert entry_write["value_json"] is None
    structured_write = next(params for _, params in writes if params["field_kind"] == "structured")
    assert json.loads(structured_write["value_json"]) == "330100"


@pytest.mark.asyncio
async def test_historical_replay_without_new_metadata_stays_compatible() -> None:
    store = ProfileStore()
    row = await store.seed_draft()
    draft = await load_owned_draft(store.session, row["draft_id"], 10)
    payload = json.loads(json.dumps(_draft_response_payload(draft)))
    for field in payload["fields"]:
        for key in ("field_kind", "profile_dimension", "category", "content", "replaces_field_key"):
            field.pop(key, None)
    restored = _draft_from_response_payload(payload, draft)
    assert restored.fields == draft.fields
    assert restored.fields[0].profile_dimension is None
    assert restored.fields[0].field_kind == "structured"
