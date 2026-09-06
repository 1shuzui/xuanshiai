"""Regression coverage for persisted MBTI results and the actual service workflow."""
import asyncio
import copy
import json
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.data.mbti_core import definition_questions
from app.schemas.auth import ProfileUpdateRequest
from app.schemas.message import EmotionAnswersUpdate, EmotionProfileSourceUpdate, MbtiResult
from app.services import emotion_lab as lab, profile


class Rows:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row

    def one(self):
        assert self.row is not None
        return self.row

    def scalar(self):
        return next(iter(self.row.values())) if self.row else None


def session_row():
    return dict(id="mbti-session-regression", user_id=101, definition_id="mbti-core",
                definition_version="mbti-core@2", result_copy_version="mbti-result-copy@2",
                status="in_progress", question_snapshot=json.dumps(definition_questions()),
                answers="[]", result_json=None, created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC))


class AssessmentStore:
    """Stateful persistence boundary; the real service owns all validation and transitions."""
    def __init__(self, row=None):
        self.row = row or session_row()
        self.source = None
        self.profile_mbti = None
        self.completions = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if sql.startswith("SELECT") and "user_mbti_profile_source" in sql:
            return Rows(self.source)
        if sql.startswith("SELECT") and "user_mbti_assessment_session" in sql:
            owned = params.get("user_id", 101) == self.row["user_id"]
            return Rows(copy.deepcopy(self.row) if owned else None)
        if sql.startswith("UPDATE user_mbti_assessment_session"):
            self.row["answers"] = params["answers"]
            if "result_json" in params:
                self.row.update(result_json=params["result_json"], status="completed")
                self.completions += 1
        if sql.startswith("INSERT INTO user_mbti_profile_source"):
            self.source = {**params, "confirmed_at": datetime.now(UTC)}
        if sql.startswith("INSERT INTO user_profile"):
            self.profile_mbti = params["mbti_type"]
        return Rows()

    async def commit(self):
        pass


def all_answers():
    return EmotionAnswersUpdate(answers=[{"questionId": q["id"], "value": 4}
                                         for q in definition_questions()])


def test_result_json_accepts_both_wire_and_legacy_storage_names():
    result = lab._score(session_id="s", questions=definition_questions(),
                        answers=all_answers().model_dump(by_alias=True)["answers"])
    assert MbtiResult.model_validate(result.model_dump(by_alias=True)) == result
    assert MbtiResult.model_validate(result.model_dump()) == result


def test_mysql_json_object_key_order_cannot_change_mbti_letter_order():
    from app.data.mbti_copy_v2 import DIMENSION_POLES, DISCLAIMER, RESULT_COPY_VERSION, RESULT_SUMMARIES
    # MySQL JSON objects do not preserve insertion order. Reproduce its canonical
    # order at the persistence boundary, without relying on Python dict ordering.
    stored = json.loads(json.dumps({'questions': definition_questions(), 'dimensionPoles': DIMENSION_POLES,
        'resultCopy': {'version': RESULT_COPY_VERSION, 'summaries': RESULT_SUMMARIES, 'disclaimer': DISCLAIMER}}, sort_keys=True))
    scored = lab._score(session_id='mysql-json', questions=stored['questions'],
        answers=all_answers().model_dump(by_alias=True)['answers'], scoring_snapshot=stored)
    assert scored.mbti_type == 'ESTJ'


def test_submit_summary_confirm_and_idempotent_retry(monkeypatch):
    async def recalculate(*_):
        return 100
    monkeypatch.setattr(lab, "recalculate_completion", recalculate)
    async def workflow():
        store = AssessmentStore()
        submitted = await lab.submit_assessment(store, 101, store.row["id"], all_answers())
        assert submitted.status == "completed"
        summary = await lab.get_summary(store, 101)
        assert summary.active_session.result == submitted.result
        confirmed = await lab.set_profile_source(store, 101, EmotionProfileSourceUpdate(
            mbtiType=submitted.result.mbti_type, source="assessment", confirmed=True,
            resultId=submitted.result.id))
        assert confirmed.mbti_type == store.profile_mbti
        repeated = await lab.submit_assessment(store, 101, store.row["id"], all_answers())
        assert repeated.result == submitted.result
        assert store.completions == 1
        with pytest.raises(HTTPException) as forbidden:
            await lab.submit_assessment(store, 102, store.row["id"], all_answers())
        assert forbidden.value.status_code == 404
    asyncio.run(workflow())


def test_half_percent_rounding_matches_frontend():
    questions = definition_questions()
    answers = [{"questionId": q["id"], "value": (1 if q["direction"] == 1 else 7)}
               for q in questions]
    ei = [i for i, q in enumerate(questions) if q["dimension"] == "EI"]
    for index, contribution in zip(ei, [6, 3]):
        answers[index]["value"] = 1 + contribution if questions[index]["direction"] == 1 else 7 - contribution
    result = lab._score(session_id="round", questions=questions, answers=answers)
    assert result.dimensions["EI"] == {"E": 13, "I": 87}


def test_old_session_keeps_original_definition_and_copy(monkeypatch):
    store = AssessmentStore()
    expected_copy = dict(lab.RESULT_SUMMARIES)
    monkeypatch.setattr(lab, "DEFINITION_VERSION", "mbti-core@future")
    monkeypatch.setattr(lab, "RESULT_COPY_VERSION", "copy@future")
    monkeypatch.setattr(lab, "RESULT_SUMMARIES", {key: "NEW COPY" for key in expected_copy})
    result = asyncio.run(lab.submit_assessment(store, 101, store.row["id"], all_answers())).result
    assert result.assessment_version == "mbti-core@2"
    assert result.result_copy.version == "mbti-result-copy@2"
    assert result.result_copy.summary == expected_copy[result.mbti_type]


def test_unconfirmed_generic_profile_patch_cannot_change_mbti(monkeypatch):
    async def recalculate(*_):
        return 100
    async def read_profile(*_):
        return {"mbti": "ENFP"}
    monkeypatch.setattr(profile, "recalculate_completion", recalculate)
    monkeypatch.setattr(profile, "get_profile", read_profile)
    class Store:
        writes = []
        async def execute(self, statement, params=None):
            sql = str(statement)
            if sql.startswith("SELECT"):
                return Rows({"mbti": "INTJ"})
            self.writes.append(sql)
            return Rows()
        async def commit(self):
            pass
    store = Store()
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(profile.update_profile(store, 101, ProfileUpdateRequest(mbti="ENFP")))
    assert rejected.value.status_code == 422
    assert store.writes == []
