"""Parent delegation over the existing child account, discovery and message state.

The relationship is re-read and locked before every delegated mutation. A parent
never becomes a child merely by submitting an ID; consent is issued by that child.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser
from app.schemas import parent as schema
from app.schemas.auth import ProfileUpdateRequest
from app.schemas.discovery import ApplicationCreateRequest, DiscoveryFilters
from app.schemas.social import BlockRequest, ReportRequest
from app.services import discovery, message, profile, regions, social

CONSENT_VERSION = "parent-consent@1"
CONSENT_SCOPES = ["查看及完善资料", "查看推荐及管理喜欢", "申请和处理认识申请", "双方同意后文字聊天", "举报和屏蔽"]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC).replace(tzinfo=None) if value and value.tzinfo else value


def _iso(value: datetime | None) -> str:
    return _naive(value).isoformat(timespec="milliseconds") + "Z" if value else ""


def _effective_status(row: dict[str, Any]) -> str:
    if row["status"] == "granted" and (not row.get("expires_at") or _naive(row["expires_at"]) <= _now()):
        return "expired"
    return row["status"]


async def _relationship(db: AsyncSession, parent_id: int, *, lock: bool = False) -> dict[str, Any] | None:
    row = (await db.execute(text("SELECT * FROM parent_relationship WHERE parent_id = :parent_id" +
        (" FOR UPDATE" if lock else "")), {"parent_id": parent_id})).mappings().first()
    if not row:
        return None
    data = dict(row)
    eligibility = (await db.execute(text("""SELECT pu.status AS parent_status,
        COALESCE(pa.realname_status, 0) AS parent_realname_status,
        cu.status AS child_status, COALESCE(ca.realname_status, 0) AS child_realname_status
        FROM users pu LEFT JOIN user_auth pa ON pa.user_id = pu.id
        LEFT JOIN users cu ON cu.id = :child_id LEFT JOIN user_auth ca ON ca.user_id = cu.id
        WHERE pu.id = :parent_id"""), {"parent_id": parent_id, "child_id": data.get("child_id")})).mappings().first()
    if eligibility:
        data.update(dict(eligibility))
    return data


def _has_live_consent(row: dict[str, Any] | None, parent_id: int, child_id: int | None = None) -> bool:
    return not (not row or row["parent_id"] != parent_id or _effective_status(row) != "granted"
        or not row.get("child_id") or (child_id is not None and row["child_id"] != child_id)
        or row.get("parent_status") != 1 or row.get("child_status") != 1
        or row.get("parent_realname_status") != 2 or row.get("child_realname_status") != 2
        or row.get("consent_version") != CONSENT_VERSION)


async def authorize_parent(db: AsyncSession, current: CurrentUser, child_id: int | None = None) -> dict[str, Any]:
    row = await _relationship(db, current.id, lock=True)
    if not _has_live_consent(row, current.id, child_id):
        raise HTTPException(403, detail="父母实名或子女授权已失效，请重新取得授权")
    return row


async def _event(db, actor_id: int, parent_id: int, child_id: int | None, action: str, target_id: int | None = None):
    await db.execute(text("""INSERT INTO parent_action_event (actor_id, parent_id, child_id, action, target_id)
        VALUES (:actor_id, :parent_id, :child_id, :action, :target_id)"""),
        dict(actor_id=actor_id, parent_id=parent_id, child_id=child_id, action=action, target_id=target_id))


async def preferences(db, user_id: int) -> schema.ParentPreference:
    row = (await db.execute(text("SELECT message_notifications, allow_parent_photo FROM parent_preferences WHERE user_id = :user_id"),
                           {"user_id": user_id})).mappings().first()
    return schema.ParentPreference(**dict(row)) if row else schema.ParentPreference()


async def update_preferences(db, current: CurrentUser, body: schema.ParentPreferenceUpdate) -> schema.ParentPreference:
    values = body.model_dump(exclude_unset=True, exclude_none=True)
    if values:
        columns = list(values)
        await db.execute(text(f"INSERT INTO parent_preferences (user_id, {', '.join(columns)}) VALUES (:user_id, " +
            ", ".join(f":{key}" for key in columns) + ") ON DUPLICATE KEY UPDATE " +
            ", ".join(f"{key} = VALUES({key})" for key in columns)),
            {"user_id": current.id, **{key: int(value) for key, value in values.items()}})
        await db.commit()
    return await preferences(db, current.id)


async def create_invitation(db, current: CurrentUser) -> schema.ParentInvitation:
    if current.realname_status != 2:
        raise HTTPException(403, detail="请先完成父母实名认证")
    await db.execute(text("INSERT IGNORE INTO parent_relationship (parent_id) VALUES (:parent_id)"), {"parent_id": current.id})
    row = await _relationship(db, current.id, lock=True)
    if row and _effective_status(row) == "granted":
        raise HTTPException(409, detail="已有有效子女授权；请在到期后续期，或先撤销授权")
    if row and row.get("invite_expires_at") and _naive(row["invite_expires_at"]) > _now() + timedelta(hours=24, seconds=-60):
        raise HTTPException(429, detail="请勿频繁生成邀请，请稍后再试")
    code = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(hours=24)
    await db.execute(text("""UPDATE parent_relationship SET invite_hash = :invite_hash,
        invite_expires_at = :expires_at, status = 'pending', updated_at = UTC_TIMESTAMP(6)
        WHERE parent_id = :parent_id"""), {"parent_id": current.id,
        "invite_hash": hashlib.sha256(code.encode()).hexdigest(), "expires_at": expires_at})
    await _event(db, current.id, current.id, row.get("child_id") if row else None, "invitation.created")
    await db.commit()
    return schema.ParentInvitation(code=code, expires_at=_iso(expires_at), consent_version=CONSENT_VERSION)


async def _invitation(db, current: CurrentUser, code: str, *, lock: bool = False) -> dict[str, Any]:
    row = (await db.execute(text("SELECT * FROM parent_relationship WHERE invite_hash = :hash" +
        (" FOR UPDATE" if lock else "")), {"hash": hashlib.sha256(code.encode()).hexdigest()})).mappings().first()
    if not row or not row.get("invite_expires_at") or _naive(row["invite_expires_at"]) <= _now():
        raise HTTPException(404, detail="邀请不存在或已失效，请向家人取得新邀请码")
    if row["parent_id"] == current.id or (row.get("child_id") and row["child_id"] != current.id):
        raise HTTPException(403, detail="该邀请不能由当前账号确认")
    if row["status"] not in ("pending", "granted"):
        raise HTTPException(409, detail="邀请已撤销")
    return dict(row)


async def preview_invitation(db, current: CurrentUser, body: schema.ParentConsentCode) -> schema.ParentConsentPreview:
    row = await _invitation(db, current, body.code)
    parent_row = (await db.execute(text("""SELECT u.nickname FROM users u JOIN user_auth a ON a.user_id = u.id
        WHERE u.id = :id AND u.status = 1 AND a.realname_status = 2"""), {"id": row["parent_id"]})).mappings().first()
    if not parent_row:
        raise HTTPException(403, detail="邀请方当前不满足授权条件")
    return schema.ParentConsentPreview(parent_id=row["parent_id"], parent_name=parent_row["nickname"] or "我的家人",
        consent_version=CONSENT_VERSION, scopes=CONSENT_SCOPES, expires_at=_iso(row["invite_expires_at"]))


async def accept_invitation(db, current: CurrentUser, body: schema.ParentConsentAccept) -> schema.ParentRelationship:
    row = await _invitation(db, current, body.code, lock=True)
    if current.realname_status != 2:
        raise HTTPException(403, detail="请先完成子女本人实名认证")
    child = (await db.execute(text("SELECT birthday FROM users WHERE id = :id AND status = 1"), {"id": current.id})).mappings().first()
    if not child or not child["birthday"] or profile._calculate_age(child["birthday"]) < 18:
        raise HTTPException(403, detail="仅成年本人可以授权")
    preview = await preview_invitation(db, current, body)
    if _effective_status(row) == "granted":
        # Retried acceptance keeps the original expiry instead of extending access.
        return schema.ParentRelationship(parent_id=row["parent_id"], parent_name=preview.parent_name,
            child_id=current.id, status="granted", expires_at=_iso(row["expires_at"]), consent_version=CONSENT_VERSION)
    expires_at = _now() + timedelta(days=body.days)
    await db.execute(text("""UPDATE parent_relationship SET child_id = :child_id, status = 'granted',
        expires_at = :expires_at, consent_version = :version, updated_at = UTC_TIMESTAMP(6)
        WHERE parent_id = :parent_id"""), {"child_id": current.id, "expires_at": expires_at,
        "version": CONSENT_VERSION, "parent_id": row["parent_id"]})
    await _event(db, current.id, row["parent_id"], current.id, "consent.granted")
    await db.commit()
    return schema.ParentRelationship(parent_id=row["parent_id"], parent_name=preview.parent_name,
        child_id=current.id, status="granted", expires_at=_iso(expires_at), consent_version=CONSENT_VERSION)


async def relationship_page(db, current: CurrentUser) -> schema.ParentRelationshipPage:
    rows = (await db.execute(text("""SELECT r.*, u.nickname AS parent_name FROM parent_relationship r
        JOIN users u ON u.id = r.parent_id WHERE r.child_id = :user_id OR r.parent_id = :user_id
        ORDER BY r.updated_at DESC"""), {"user_id": current.id})).mappings().all()
    return schema.ParentRelationshipPage(items=[schema.ParentRelationship(
        parent_id=row["parent_id"], parent_name=row["parent_name"] or "我的家人", child_id=row["child_id"],
        status=_effective_status(dict(row)), expires_at=_iso(row["expires_at"]), consent_version=row["consent_version"])
        for row in rows])


async def revoke_relationship(db, current: CurrentUser, parent_id: int) -> schema.ParentSuccess:
    row = await _relationship(db, parent_id, lock=True)
    if not row or current.id not in (row["parent_id"], row.get("child_id")):
        raise HTTPException(404, detail="授权关系不存在")
    if row["status"] != "revoked":
        await db.execute(text("""UPDATE parent_relationship SET status = 'revoked', invite_hash = NULL,
            invite_expires_at = NULL, updated_at = UTC_TIMESTAMP(6) WHERE parent_id = :parent_id"""), {"parent_id": parent_id})
        await _event(db, current.id, parent_id, row.get("child_id"), "consent.revoked")
        await db.commit()
    return schema.ParentSuccess()


async def remaining_applications(db, child_id: int) -> int:
    used = int((await db.execute(text("""SELECT COUNT(*) FROM match_apply WHERE from_user_id = :child_id
        AND created_at >= UTC_DATE() AND status IN (0, 1, 3)"""), {"child_id": child_id})).scalar() or 0)
    return max(0, 3 - used)


def _city_name(code: str | None) -> str:
    for province in regions._REGIONS:
        for city in province.get("children", []):
            if str(city["code"]) == code:
                return city["name"]
    return "未填写"


def _city_codes(value: str) -> tuple[str, str]:
    matches = [(str(province["code"]), str(city["code"])) for province in regions._REGIONS
               for city in province.get("children", []) if value in (str(city["code"]), city["name"], city["name"].removesuffix("市"))]
    if len(matches) != 1:
        raise HTTPException(422, detail="请填写有效的城市名称或城市编码")
    return matches[0]


async def get_context(db, current: CurrentUser) -> schema.ParentContext:
    user = (await db.execute(text("SELECT nickname FROM users WHERE id = :id"), {"id": current.id})).mappings().first()
    pref = await preferences(db, current.id)
    context = schema.ParentContext(id=f"parent:{current.id}", parent=schema.ParentIdentity(id=current.id,
        name=user["nickname"] or "我的家人" if user else "我的家人",
        real_name_status={0: "missing", 1: "reviewing", 2: "passed", 3: "rejected"}.get(current.realname_status, "missing")),
        quota=schema.ParentQuota(remaining_applications=0), message_notifications=pref.message_notifications)
    row = await _relationship(db, current.id, lock=True)
    if not row or not row.get("child_id"):
        return context
    status = _effective_status(row)
    eligible = _has_live_consent(row, current.id)
    child = await profile.get_profile(db, row["child_id"]) if eligible else {}
    context.child = schema.ParentChild(id=row["child_id"], display_name=child.get("nickname") or "子女授权未生效",
        birth_year=child["birthday"].year if child.get("birthday") else 0,
        city=_city_name(child.get("residence_city_code")) if eligible else "", job=child.get("occupation") or "",
        introduction=child.get("self_intro") or "", authorization_status=status if eligible or status != "granted" else "revoked",
        authorization_expires_at=_iso(row.get("expires_at")), profile_progress=child.get("completion_score") or 0)
    if eligible:
        context.quota.remaining_applications = await remaining_applications(db, row["child_id"])
    return context


async def update_child(db, current: CurrentUser, child_id: int, body: schema.ParentChildUpdate) -> schema.ParentChild:
    await authorize_parent(db, current, child_id)
    child = await profile.get_profile(db, child_id)
    if not child.get("birthday") or child["birthday"].year != body.birth_year:
        raise HTTPException(422, detail="已核验出生信息仅可由本人通过认证流程更正")
    if not body.display_name or not body.city:
        raise HTTPException(422, detail="称呼和城市不能为空")
    province_code, city_code = _city_codes(body.city)
    await db.execute(text("UPDATE users SET nickname = :name WHERE id = :child_id"), {"name": body.display_name, "child_id": child_id})
    await _event(db, current.id, current.id, child_id, "profile.updated", child_id)
    await profile.update_profile(db, child_id, ProfileUpdateRequest(occupation=body.job, self_intro=body.introduction,
        residence_province_code=province_code, residence_city_code=city_code))
    return (await get_context(db, current)).child


def _candidate(card: Any, row: dict[str, Any]) -> schema.ParentCandidate:
    education = {1: "博士", 2: "硕士", 3: "本科", 4: "大专", 5: "高中"}
    return schema.ParentCandidate(id=card.user_id, display_name=card.nickname or "未公开称呼",
        gender_text={1: "男", 2: "女"}.get(row.get("gender"), "未公开"),
        birth_year=row["birthday"].year if row.get("birthday") else 0,
        city=_city_name(card.city_code), height=f"{card.height}cm" if card.height else "未公开",
        education=education.get(card.education_level, "未公开"), job=card.occupation or "未公开",
        certification_text=" · ".join(card.certification_tags) or "认证状态以平台核验为准")


async def candidates(db, current: CurrentUser, child_id: int, page: int, page_size: int, liked: bool = False):
    await authorize_parent(db, current, child_id)
    if liked:
        source = await social.list_relation(db, child_id, "like", False, page, page_size)
    else:
        source = await discovery.get_discovery_page(db, child_id, DiscoveryFilters(page=page, page_size=page_size), plaza=False)
    ids = [item.user_id for item in source.items]
    rows = await discovery._target_rows(db, child_id, ids)
    vip = await discovery._is_vip(db, child_id) if liked else False
    items = []
    for card in source.items:
        row = rows.get(card.user_id)
        if not row:
            continue
        if liked:
            card = discovery._card(row, 0, "", detail_locked=bool(row.get("only_vip_can_see_detail")) and not vip)
        items.append(_candidate(card, row))
    liked_ids = set(ids) if liked else set()
    if ids and not liked:
        params = {"child": child_id, **{f"id{i}": value for i, value in enumerate(ids)}}
        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        liked_ids = set((await db.execute(text("SELECT target_user_id FROM user_favorite WHERE user_id = :child "
            f"AND type = 1 AND target_user_id IN ({placeholders})"), params)).scalars().all())
    for item in items:
        item.liked = item.id in liked_ids
    return schema.ParentCandidatePage(items=items, page=page, page_size=page_size, total=source.total, has_more=page * page_size < source.total)


async def candidate_detail(db, current: CurrentUser, child_id: int, target_id: int):
    await authorize_parent(db, current, child_id)
    source = await discovery.view_profile(db, child_id, target_id)
    # The shared browsing service commits its own visit record.
    await authorize_parent(db, current, child_id)
    row = (await discovery._target_rows(db, child_id, [target_id])).get(target_id)
    if row is None:
        raise HTTPException(404, detail="用户不存在或当前不可见")
    result = _candidate(source.card, row)
    if source.profile:
        result.introduction = source.profile.self_intro or ""
    pref = await preferences(db, target_id)
    if pref.allow_parent_photo and not source.card.detail_locked:
        result.clear_avatar = source.card.avatar or ""
        result.can_view_clear_photo = bool(result.clear_avatar)
    result.liked = bool((await db.execute(text("SELECT 1 FROM user_favorite WHERE user_id = :child AND target_user_id = :target AND type = 1"),
        {"child": child_id, "target": target_id})).scalar())
    return result


async def set_like(db, current: CurrentUser, child_id: int, target_id: int, body: schema.ParentLikeRequest):
    await authorize_parent(db, current, child_id)
    await _event(db, current.id, current.id, child_id, "like.enabled" if body.liked else "like.disabled", target_id)
    await social.set_like(db, child_id, target_id, body.liked)
    return schema.ParentLikeResult(user_id=target_id, liked=body.liked)


async def create_application(db, current: CurrentUser, child_id: int, target_id: int, body: schema.ParentApplyRequest):
    await authorize_parent(db, current, child_id)
    await discovery._lock_user_pair(db, child_id, target_id)
    await discovery._ensure_target(db, child_id, target_id)
    await discovery._expire_pending_applications(db)
    existing = (await db.execute(text("""SELECT id, message FROM match_apply WHERE from_user_id = :child_id
        AND to_user_id = :target_id AND status = 0 ORDER BY id DESC LIMIT 1"""),
        {"child_id": child_id, "target_id": target_id})).mappings().first()
    if existing:
        if (existing["message"] or "") != body.note:
            raise HTTPException(409, detail="已有待回应申请；不能用重试修改附言")
        return schema.ParentApplyResult(application_id=existing["id"], remaining_applications=await remaining_applications(db, child_id), deduplicated=True)
    if await remaining_applications(db, child_id) <= 0:
        raise HTTPException(429, detail="今日申请次数已用完")
    await _event(db, current.id, current.id, child_id, "application.created", target_id)
    created = await discovery.create_application(db, child_id, target_id, ApplicationCreateRequest(message=body.note))
    return schema.ParentApplyResult(application_id=created.id, remaining_applications=await remaining_applications(db, child_id))


async def block_candidate(db, current: CurrentUser, child_id: int, target_id: int):
    await authorize_parent(db, current, child_id)
    await _event(db, current.id, current.id, child_id, "candidate.blocked", target_id)
    await social.set_block(db, child_id, target_id, BlockRequest(reason="父母协助屏蔽"), True)
    return schema.ParentSuccess()


async def report_candidate(db, current: CurrentUser, child_id: int, target_id: int, body: schema.ParentReportRequest):
    # Reporting stays available after revocation; it is always filed as the reporting parent.
    row = await _relationship(db, current.id)
    if not row or row.get("child_id") != child_id:
        raise HTTPException(403, detail="无权使用该子女上下文")
    await _event(db, current.id, current.id, child_id, "candidate.reported", target_id)
    return await social.create_report(db, current.id, target_id, ReportRequest(type=body.reason_id, description=body.detail))


_PRIVATE_KEYS = {"avatar", "avatarurl", "clearavatar", "senderavatar", "receiveravatar", "photourl",
                 "phone", "phonenumber", "wechat", "contactvalue", "mediaurl", "imageurl", "url", "fileurl",
                 "photos", "media", "attachments", "voiceurl", "videourl", "thumbnail", "coverurl"}


def protect_parent_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(by_alias=True, mode="json")
    if isinstance(value, list):
        return [protect_parent_payload(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: protect_parent_payload(item) for key, item in value.items()
              if key.replace("_", "").lower() not in _PRIVATE_KEYS}
    for key in ("avatar", "senderAvatar"):
        if key in value: result[key] = ""
    if value.get("type") in ("image", "voice", "video"):
        result["content"] = ""
        result["protectedContent"] = True
    if value.get("messageType") in ("image", "voice", "video"):
        result["lastMessage"] = "[受保护的消息]"
    return result


async def message_guard(db, current: CurrentUser, child_id: int, action: str, target_id: int | None = None):
    await authorize_parent(db, current, child_id)
    if target_id is not None:
        await social.ensure_users_can_interact(db, child_id, target_id)
    await _event(db, current.id, current.id, child_id, action, target_id)


async def alerts(db, current: CurrentUser, child_id: int) -> schema.ParentAlerts:
    await authorize_parent(db, current, child_id)
    pref = await preferences(db, current.id)
    latest = int((await db.execute(text("""SELECT COALESCE(MAX(id), 0) FROM user_notification
        WHERE user_id = :child_id AND notification_type IN
        ('message', 'match_application', 'match_application_accepted', 'match_application_rejected')"""),
        {"child_id": child_id})).scalar() or 0)
    return schema.ParentAlerts(enabled=pref.message_notifications, latest_event_id=latest,
        unread_count=await message._unread_total(db, child_id), pending_count=await message._incoming_pending_count(db, child_id))
