"""Versioned MBTI assessment sessions and explicit profile-source confirmation."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.mbti_core import (
    DEFINITION_ID,
    DEFINITION_VERSION,
    DIMENSION_POLES,
    RESULT_COPY_VERSION,
    RESULT_SUMMARIES,
    SCALE_MAX,
    SCALE_MIN,
    definition_questions,
)
from app.schemas.message import (
    EmotionAnswersUpdate,
    EmotionAssessmentDefinition,
    EmotionLabSummary,
    EmotionProfileSource,
    EmotionProfileSourceUpdate,
    EmotionSessionCreate,
    EmotionSessionSnapshot,
    MbtiAnswer,
    MbtiResult,
    MbtiResultCopy,
)
from app.services.profile import recalculate_completion
from app.data import mbti_copy_v2


DISCLAIMER = "结果仅用于自我了解，不构成心理诊断或专业建议。"


def _timestamp(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


def _definition() -> EmotionAssessmentDefinition:
    return EmotionAssessmentDefinition(
        id=DEFINITION_ID,
        version=DEFINITION_VERSION,
        title="MBTI 基础维度测试",
        authorization={
            "status": "approved",
            "label": "内容已授权",
            "reviewedAt": None,
        },
        can_start=True,
        question_count=len(definition_questions()),
        scale={"min": SCALE_MIN, "max": SCALE_MAX},
        dimensions=list(DIMENSION_POLES),
        tie_break="first_pole",
        result_copy_version=RESULT_COPY_VERSION,
    )


def _json(value: Any, label: str) -> Any:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HTTPException(500, detail=f"{label}数据损坏") from exc
    return value


def _public_questions(snapshot: Any) -> list[dict[str, Any]]:
    if not isinstance(snapshot, list):
        raise HTTPException(500, detail="题目快照数据损坏")
    public: list[dict[str, Any]] = []
    for item in snapshot:
        if not isinstance(item, dict):
            raise HTTPException(500, detail="题目快照数据损坏")
        public.append(
            {
                "id": item.get("id"),
                "text": item.get("text"),
                "options": item.get("options"),
            }
        )
    return public


def _answers(value: Any) -> list[dict[str, Any]]:
    parsed = _json(value, "答案")
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise HTTPException(500, detail="答案数据损坏")
    return parsed


def _scoring_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """Read a frozen session, including the immutable archive for legacy lists."""
    raw = _json(row["question_snapshot"], "题目快照")
    if isinstance(raw, list):
        if (row["definition_id"], row["definition_version"], row["result_copy_version"]) != (
            mbti_copy_v2.DEFINITION_ID, mbti_copy_v2.DEFINITION_VERSION, mbti_copy_v2.RESULT_COPY_VERSION
        ):
            raise HTTPException(409, detail="该历史测试版本暂不可用，请放弃后重新开始")
        return {"questions": raw, "dimensionPoles": deepcopy(mbti_copy_v2.DIMENSION_POLES),
                "resultCopy": {"version": mbti_copy_v2.RESULT_COPY_VERSION,
                               "summaries": deepcopy(mbti_copy_v2.RESULT_SUMMARIES),
                               "disclaimer": mbti_copy_v2.DISCLAIMER}}
    if not isinstance(raw, dict) or not isinstance(raw.get("questions"), list):
        raise HTTPException(500, detail="题目快照数据损坏")
    copy = raw.get("resultCopy", {})
    if copy.get("version") != row["result_copy_version"] or not isinstance(copy.get("summaries"), dict):
        raise HTTPException(500, detail="结果文案快照数据损坏")
    if raw.get("dimensionPoles") != {key: list(value) for key, value in mbti_copy_v2.DIMENSION_POLES.items()}:
        raise HTTPException(500, detail="计分维度快照数据损坏")
    return raw


def _snapshot(row: dict[str, Any]) -> EmotionSessionSnapshot:
    questions = _scoring_snapshot(row)["questions"]
    answers = _answers(row.get("answers"))
    result_raw = _json(row.get("result_json"), "结果") if row.get("result_json") else None
    return EmotionSessionSnapshot(
        schema_version=2,
        id=row["id"],
        definition_id=row["definition_id"],
        definition_version=row["definition_version"],
        result_copy_version=row["result_copy_version"],
        status=row["status"],
        question_ids=[item["id"] for item in questions],
        questions=_public_questions(questions),
        answers=answers,
        result=result_raw,
        created_at=_timestamp(row["created_at"]),
        updated_at=_timestamp(row["updated_at"]),
    )


async def _latest_visible_session(
    db: AsyncSession, user_id: int
) -> EmotionSessionSnapshot | None:
    result = await db.execute(
        text(
            """SELECT * FROM user_mbti_assessment_session
            WHERE user_id = :user_id AND status IN ('in_progress', 'completed')
            ORDER BY CASE status WHEN 'in_progress' THEN 0 ELSE 1 END,
                     updated_at DESC, id DESC
            LIMIT 1"""
        ),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    return _snapshot(dict(row)) if row else None


async def get_summary(db: AsyncSession, user_id: int) -> EmotionLabSummary:
    result = await db.execute(
        text(
            """SELECT mbti_type, source, assessment_version, result_id, confirmed_at
            FROM user_mbti_profile_source WHERE user_id = :user_id"""
        ),
        {"user_id": user_id},
    )
    row = result.mappings().first()
    profile_source = None
    if row:
        profile_source = EmotionProfileSource(
            mbti_type=row["mbti_type"],
            source=row["source"],
            assessment_version=row["assessment_version"],
            result_id=row["result_id"],
            confirmed_at=_timestamp(row["confirmed_at"]),
        )
    return EmotionLabSummary(
        assessments=[_definition()],
        manual_types=sorted(RESULT_SUMMARIES),
        active_session=await _latest_visible_session(db, user_id),
        profile_source=profile_source,
        disclaimer=DISCLAIMER,
        disclaimer_version=RESULT_COPY_VERSION,
    )


async def start_assessment(
    db: AsyncSession, user_id: int, request: EmotionSessionCreate
) -> EmotionSessionSnapshot:
    if request.assessment_id != DEFINITION_ID:
        raise HTTPException(404, detail="测试定义不存在")
    # Lock a stable row even when this user has no draft yet.
    await db.execute(text("SELECT id FROM users WHERE id = :user_id FOR UPDATE"), {"user_id": user_id})
    existing = await db.execute(
        text(
            """SELECT id FROM user_mbti_assessment_session
            WHERE user_id = :user_id AND status = 'in_progress'
            ORDER BY created_at DESC LIMIT 1 FOR UPDATE"""
        ),
        {"user_id": user_id},
    )
    if existing.mappings().first():
        raise HTTPException(409, detail="已有未完成测试，请先继续或放弃")
    session_id = f"mbti-session-{uuid4()}"
    questions = definition_questions()
    await db.execute(
        text(
            """INSERT INTO user_mbti_assessment_session
            (id, user_id, definition_id, definition_version, result_copy_version,
             status, question_snapshot, answers, result_json, created_at, updated_at)
            VALUES (:id, :user_id, :definition_id, :definition_version,
                    :result_copy_version, 'in_progress', :question_snapshot,
                    JSON_ARRAY(), NULL, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"""
        ),
        {
            "id": session_id,
            "user_id": user_id,
            "definition_id": DEFINITION_ID,
            "definition_version": DEFINITION_VERSION,
            "result_copy_version": RESULT_COPY_VERSION,
            "question_snapshot": json.dumps({
                "questions": questions, "dimensionPoles": DIMENSION_POLES,
                "resultCopy": {"version": RESULT_COPY_VERSION, "summaries": RESULT_SUMMARIES,
                               "disclaimer": DISCLAIMER},
            }, ensure_ascii=False),
        },
    )
    await db.commit()
    created = await db.execute(
        text("SELECT * FROM user_mbti_assessment_session WHERE id = :id"),
        {"id": session_id},
    )
    return _snapshot(dict(created.mappings().one()))


async def _owned_session(
    db: AsyncSession, user_id: int, session_id: str
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """SELECT * FROM user_mbti_assessment_session
            WHERE id = :session_id AND user_id = :user_id FOR UPDATE"""
        ),
        {"session_id": session_id, "user_id": user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, detail="测试会话不存在")
    return dict(row)


def _canonical_answers(questions: Any, answers: list[MbtiAnswer]) -> list[dict[str, int | str]]:
    if not isinstance(questions, list):
        raise HTTPException(500, detail="题目快照数据损坏")
    question_by_id: dict[str, dict[str, Any]] = {}
    for question in questions:
        if not isinstance(question, dict) or not isinstance(question.get("id"), str):
            raise HTTPException(500, detail="题目快照数据损坏")
        question_by_id[question["id"]] = question
    values: dict[str, int] = {}
    for answer in answers:
        if answer.question_id in values:
            raise HTTPException(422, detail="同一题不能重复提交")
        question = question_by_id.get(answer.question_id)
        if question is None:
            raise HTTPException(422, detail="答案不属于当前题目快照")
        allowed = {
            option.get("value")
            for option in question.get("options", [])
            if isinstance(option, dict)
        }
        if answer.value not in allowed:
            raise HTTPException(422, detail="答案不属于题目允许选项")
        values[answer.question_id] = answer.value
    return [
        {"questionId": question["id"], "value": values[question["id"]]}
        for question in questions
        if question["id"] in values
    ]


def _same_answers(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    return left == right


def _score(
    *,
    session_id: str,
    questions: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    definition_id: str = mbti_copy_v2.DEFINITION_ID,
    definition_version: str = mbti_copy_v2.DEFINITION_VERSION,
    scoring_snapshot: dict[str, Any] | None = None,
) -> MbtiResult:
    frozen = scoring_snapshot or {"dimensionPoles": mbti_copy_v2.DIMENSION_POLES,
        "resultCopy": {"version": mbti_copy_v2.RESULT_COPY_VERSION,
                       "summaries": mbti_copy_v2.RESULT_SUMMARIES, "disclaimer": mbti_copy_v2.DISCLAIMER}}
    answer_by_id = {str(answer["questionId"]): int(answer["value"]) for answer in answers}
    dimensions: dict[str, dict[str, int]] = {}
    type_letters: list[str] = []
    # MySQL normalizes JSON object keys; MBTI letter order is part of the
    # assessment contract and cannot depend on storage dictionary ordering.
    for dimension in ("EI", "SN", "TF", "JP"):
        first_pole, second_pole = frozen["dimensionPoles"][dimension]
        relevant = [question for question in questions if question.get("dimension") == dimension]
        if not relevant:
            raise HTTPException(500, detail="题目快照缺少 MBTI 维度")
        first_raw = 0
        possible = 0
        for question in relevant:
            value = answer_by_id[str(question["id"])]
            scale_min = int(question["scaleMin"])
            scale_max = int(question["scaleMax"])
            span = scale_max - scale_min
            if span <= 0 or int(question["direction"]) not in (-1, 1):
                raise HTTPException(500, detail="题目计分快照数据损坏")
            first_raw += value - scale_min if int(question["direction"]) == 1 else scale_max - value
            possible += span
        # Positive integer half-up, identical to frontend Math.round without float drift.
        first_score = (first_raw * 200 + possible) // (2 * possible)
        dimensions[dimension] = {first_pole: first_score, second_pole: 100 - first_score}
        type_letters.append(first_pole if first_score >= 50 else second_pole)
    mbti_type = "".join(type_letters)
    completed_at = int(datetime.now(UTC).timestamp() * 1000)
    return MbtiResult(
        id=f"mbti-result:{session_id}",
        session_id=session_id,
        assessment_id=definition_id,
        assessment_version=definition_version,
        mbti_type=mbti_type,
        dimensions=dimensions,
        result_copy=MbtiResultCopy(
            version=frozen["resultCopy"]["version"],
            title=f"{mbti_type} · MBTI 偏好结果",
            summary=frozen["resultCopy"]["summaries"][mbti_type],
            disclaimer=frozen["resultCopy"]["disclaimer"],
        ),
        completed_at=completed_at,
    )


async def save_answers(
    db: AsyncSession, user_id: int, session_id: str, request: EmotionAnswersUpdate
) -> EmotionSessionSnapshot:
    row = await _owned_session(db, user_id, session_id)
    if row["status"] == "completed":
        raise HTTPException(409, detail="测试已经提交")
    if row["status"] == "discarded":
        raise HTTPException(409, detail="测试会话已放弃")
    questions = _scoring_snapshot(row)["questions"]
    incoming = _canonical_answers(questions, request.answers)
    existing = _answers(row.get("answers"))
    merged = {str(answer["questionId"]): int(answer["value"]) for answer in existing}
    merged.update({str(answer["questionId"]): int(answer["value"]) for answer in incoming})
    ordered = [
        {"questionId": question["id"], "value": merged[question["id"]]}
        for question in questions
        if question["id"] in merged
    ]
    await db.execute(
        text(
            """UPDATE user_mbti_assessment_session
            SET answers = :answers, updated_at = UTC_TIMESTAMP(6) WHERE id = :session_id"""
        ),
        {"session_id": session_id, "answers": json.dumps(ordered, ensure_ascii=False)},
    )
    await db.commit()
    updated = await db.execute(
        text("SELECT * FROM user_mbti_assessment_session WHERE id = :id"), {"id": session_id}
    )
    return _snapshot(dict(updated.mappings().one()))


async def submit_assessment(
    db: AsyncSession, user_id: int, session_id: str, request: EmotionAnswersUpdate
) -> EmotionSessionSnapshot:
    row = await _owned_session(db, user_id, session_id)
    frozen = _scoring_snapshot(row)
    questions = frozen["questions"]
    submitted = _canonical_answers(questions, request.answers)
    if len(submitted) != len(questions):
        raise HTTPException(422, detail="必须完成全部题目后提交")
    existing = _answers(row.get("answers"))
    if row["status"] == "completed":
        if _same_answers(existing, submitted):
            return _snapshot(row)
        raise HTTPException(409, detail="已完成测试不能更改答案")
    if row["status"] == "discarded":
        raise HTTPException(409, detail="测试会话已放弃")
    result = _score(session_id=session_id, questions=questions, answers=submitted,
                    definition_id=row["definition_id"], definition_version=row["definition_version"],
                    scoring_snapshot=frozen)
    result_data = result.model_dump(by_alias=True, mode="json")
    await db.execute(
        text(
            """UPDATE user_mbti_assessment_session
            SET status = 'completed', answers = :answers, result_json = :result_json,
                completed_at = UTC_TIMESTAMP(6), updated_at = UTC_TIMESTAMP(6)
            WHERE id = :session_id"""
        ),
        {
            "session_id": session_id,
            "answers": json.dumps(submitted, ensure_ascii=False),
            "result_json": json.dumps(result_data, ensure_ascii=False),
        },
    )
    await db.execute(
        text(
            """INSERT INTO user_mbti_result
            (user_id, mbti_type, ei_score, sn_score, tf_score, jp_score, dimensions,
             description, test_version, test_date)
            VALUES (:user_id, :mbti_type, :ei_score, :sn_score, :tf_score, :jp_score,
                    :dimensions, :description, :test_version, UTC_DATE())
            ON DUPLICATE KEY UPDATE mbti_type = VALUES(mbti_type),
                ei_score = VALUES(ei_score), sn_score = VALUES(sn_score),
                tf_score = VALUES(tf_score), jp_score = VALUES(jp_score),
                dimensions = VALUES(dimensions), description = VALUES(description),
                test_version = VALUES(test_version)"""
        ),
        {
            "user_id": user_id,
            "mbti_type": result.mbti_type,
            "ei_score": result.dimensions["EI"]["E"],
            "sn_score": result.dimensions["SN"]["S"],
            "tf_score": result.dimensions["TF"]["T"],
            "jp_score": result.dimensions["JP"]["J"],
            "dimensions": json.dumps(result.dimensions),
            "description": result.result_copy.summary,
            "test_version": result.assessment_version,
        },
    )
    await db.commit()
    updated = await db.execute(
        text("SELECT * FROM user_mbti_assessment_session WHERE id = :id"), {"id": session_id}
    )
    return _snapshot(dict(updated.mappings().one()))


async def discard_assessment(
    db: AsyncSession, user_id: int, session_id: str
) -> EmotionSessionSnapshot:
    row = await _owned_session(db, user_id, session_id)
    if row["status"] == "completed":
        raise HTTPException(409, detail="测试已经提交，不能放弃")
    if row["status"] == "discarded":
        return _snapshot(row)
    await db.execute(
        text(
            """UPDATE user_mbti_assessment_session
            SET status = 'discarded', answers = JSON_ARRAY(), updated_at = UTC_TIMESTAMP(6)
            WHERE id = :session_id"""
        ),
        {"session_id": session_id},
    )
    await db.commit()
    updated = await db.execute(
        text("SELECT * FROM user_mbti_assessment_session WHERE id = :id"), {"id": session_id}
    )
    return _snapshot(dict(updated.mappings().one()))


async def set_profile_source(
    db: AsyncSession, user_id: int, request: EmotionProfileSourceUpdate
) -> EmotionProfileSource:
    if not request.confirmed:
        raise HTTPException(422, detail="同步资料前需要明确确认")
    await db.execute(text("SELECT id FROM users WHERE id = :user_id FOR UPDATE"), {"user_id": user_id})
    assessment_version: str | None = None
    result_id: str | None = None
    if request.source == "assessment":
        if not request.result_id or not request.result_id.startswith("mbti-result:"):
            raise HTTPException(422, detail="同步测评结果需要有效结果记录")
        session_id = request.result_id.removeprefix("mbti-result:")
        result = await db.execute(
            text(
                """SELECT result_json FROM user_mbti_assessment_session
                WHERE id = :session_id AND user_id = :user_id AND status = 'completed'"""
            ),
            {"session_id": session_id, "user_id": user_id},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(422, detail="同步测评结果需要有效结果记录")
        completed = MbtiResult.model_validate(_json(row["result_json"], "结果"))
        if completed.id != request.result_id or completed.mbti_type != request.mbti_type:
            raise HTTPException(422, detail="测评结果与待同步类型不一致")
        assessment_version = completed.assessment_version
        result_id = completed.id
    confirmed_at = datetime.now(UTC).replace(tzinfo=None)
    await db.execute(
        text(
            """INSERT INTO user_mbti_profile_source
            (user_id, mbti_type, source, assessment_version, result_id, confirmed_at)
            VALUES (:user_id, :mbti_type, :source, :assessment_version, :result_id, :confirmed_at)
            ON DUPLICATE KEY UPDATE mbti_type = VALUES(mbti_type), source = VALUES(source),
                assessment_version = VALUES(assessment_version), result_id = VALUES(result_id),
                confirmed_at = VALUES(confirmed_at)"""
        ),
        {
            "user_id": user_id,
            "mbti_type": request.mbti_type,
            "source": request.source,
            "assessment_version": assessment_version,
            "result_id": result_id,
            "confirmed_at": confirmed_at,
        },
    )
    await db.execute(
        text(
            """INSERT INTO user_profile (user_id, mbti)
            VALUES (:user_id, :mbti_type)
            ON DUPLICATE KEY UPDATE mbti = VALUES(mbti)"""
        ),
        {"user_id": user_id, "mbti_type": request.mbti_type},
    )
    await recalculate_completion(db, user_id)
    await db.commit()
    return EmotionProfileSource(
        mbti_type=request.mbti_type,
        source=request.source,
        assessment_version=assessment_version,
        result_id=result_id,
        confirmed_at=_timestamp(confirmed_at),
    )
