"""Ordinary-user message centre adapters built on the existing social services."""

from __future__ import annotations
from collections.abc import Awaitable, Callable

import re
from datetime import UTC, datetime
from typing import Any

from cryptography.fernet import InvalidToken
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_sensitive, encrypt_sensitive
from app.schemas.message import (
    ApplicationHandleResult,
    ChatPermissionResponse,
    ContactExchange,
    ContactExchangeCreateRequest,
    ContactExchangeRespondRequest,
    MarkAllReadResult,
    MessageApplication,
    MessageApplicationPage,
    MessageChatItem,
    MessageConversation,
    MessageConversationPage,
    MessageRevokeResult,
    MessageSendRequest,
    MessageSendResult,
)
from app.schemas.social import ChatMessageCreate
from app.services import discovery, social
from app.services.community_media import bind_media, resolve_owned_ready_media
from app.services.idempotency import abort, complete, reserve_or_replay


APPLICATION_STATUS = {
    0: ("pending", "待处理"),
    1: ("accepted", "已同意"),
    2: ("rejected", "已拒绝"),
    3: ("expired", "已过期"),
}
CHAT_TYPE = {"text": 1, "image": 2, "voice": 3, "video": 4}
CHAT_TYPE_NAME = {value: key for key, value in CHAT_TYPE.items()}


def _cursor_offset(cursor: str) -> int:
    normalized = (cursor or "").strip()
    if normalized and not re.fullmatch(r"[0-9]{1,9}", normalized):
        raise HTTPException(422, detail="分页游标无效")
    return int(normalized or "0")


def _timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


def _page(cursor: str, page_size: int) -> tuple[int, int]:
    offset = _cursor_offset(cursor)
    if offset % page_size != 0:
        raise HTTPException(422, detail="分页游标与页大小不匹配")
    return offset, offset // page_size + 1


def _model_payload(model: Any) -> dict[str, Any]:
    return model.model_dump(by_alias=True, mode="json")


async def _target_summaries(
    db: AsyncSession, user_ids: list[int]
) -> dict[int, dict[str, Any]]:
    if not user_ids:
        return {}
    unique_ids = list(dict.fromkeys(user_ids))
    placeholders = ", ".join(f":user_id_{index}" for index in range(len(unique_ids)))
    result = await db.execute(
        text(
            f"""SELECT id, nickname, avatar FROM users
            WHERE id IN ({placeholders}) AND status = 1"""
        ),
        {f"user_id_{index}": value for index, value in enumerate(unique_ids)},
    )
    return {int(row["id"]): dict(row) for row in result.mappings().all()}


async def _unread_total(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        text(
            """SELECT COUNT(*) FROM chat_message m
            JOIN chat_session s ON s.id = m.session_id
            WHERE m.to_user_id = :user_id AND m.is_read = 0
              AND ((s.user1_id = :user_id AND m.from_user_id = s.user2_id)
                OR (s.user2_id = :user_id AND m.from_user_id = s.user1_id))
              AND EXISTS (
                SELECT 1 FROM user_match um
                WHERE um.user_id = :user_id
                  AND um.target_user_id = m.from_user_id
                  AND um.status IN (1, 2)
              )
              AND NOT EXISTS (
                SELECT 1 FROM user_block ub
                WHERE (ub.user_id = :user_id AND ub.target_user_id = m.from_user_id)
                   OR (ub.user_id = m.from_user_id AND ub.target_user_id = :user_id)
              )"""
        ),
        {"user_id": user_id},
    )
    return int(result.scalar() or 0)


async def get_chat_permission(
    db: AsyncSession, user_id: int, peer_user_id: int
) -> ChatPermissionResponse:
    if user_id == peer_user_id:
        return ChatPermissionResponse(
            user_id=peer_user_id,
            can_chat=False,
            reason="当前没有聊天权限",
        )
    result = await db.execute(
        text(
            """SELECT s.id FROM chat_session s
            WHERE ((s.user1_id = :user_id AND s.user2_id = :peer_user_id)
                OR (s.user2_id = :user_id AND s.user1_id = :peer_user_id))
              AND EXISTS (
                SELECT 1 FROM user_match um
                WHERE um.user_id = :user_id AND um.target_user_id = :peer_user_id
                  AND um.status IN (1, 2)
              )
              AND NOT EXISTS (
                SELECT 1 FROM user_block ub
                WHERE (ub.user_id = :user_id AND ub.target_user_id = :peer_user_id)
                   OR (ub.user_id = :peer_user_id AND ub.target_user_id = :user_id)
              )
            LIMIT 1"""
        ),
        {"user_id": user_id, "peer_user_id": peer_user_id},
    )
    session_id = result.scalar()
    if session_id is None:
        return ChatPermissionResponse(
            user_id=peer_user_id,
            can_chat=False,
            reason="双方同意后才能开始聊天",
        )
    return ChatPermissionResponse(
        user_id=peer_user_id,
        conversation_id=f"message-session:{int(session_id)}",
        session_id=int(session_id),
        can_chat=True,
        reason="",
    )


async def get_conversation_page(
    db: AsyncSession, user_id: int, cursor: str, page_size: int
) -> MessageConversationPage:
    offset, page = _page(cursor, page_size)
    source = await social.list_chat_sessions(db, user_id, page, page_size)
    conversations = [
        MessageConversation(
            id=item.id,
            conversation_id=f"message-session:{item.id}",
            user_id=item.target.user_id,
            avatar=item.target.avatar,
            name=item.target.nickname or f"用户{item.target.user_id}",
            last_message=item.last_message or "已同意认识，可以开始聊天。",
            time=_timestamp(item.last_message_time),
            unread_count=item.unread_count,
        )
        for item in source.items
    ]
    return MessageConversationPage(
        list=conversations,
        next_cursor=str(offset + len(conversations)) if source.has_more else "",
        has_more=source.has_more,
        total=source.total,
        unread_total=await _unread_total(db, user_id),
    )


def _application_item(row: Any, incoming: bool, target: dict[str, Any] | None) -> MessageApplication:
    status, status_text = APPLICATION_STATUS[int(row.status)]
    peer_id = int(row.from_user_id if incoming else row.to_user_id)
    return MessageApplication(
        id=int(row.id),
        user_id=peer_id,
        avatar=target.get("avatar") if target else None,
        name=(target.get("nickname") if target else None) or f"用户{peer_id}",
        message=row.message or "",
        time=_timestamp(row.created_at),
        status=status,
        status_text=status_text,
        direction="in" if incoming else "out",
    )


async def _incoming_pending_count(db: AsyncSession, user_id: int) -> int:
    await discovery._expire_pending_applications(db)
    result = await db.execute(
        text(
            """SELECT COUNT(*) FROM match_apply
            WHERE to_user_id = :user_id AND status = 0"""
        ),
        {"user_id": user_id},
    )
    return int(result.scalar() or 0)


async def get_application_page(
    db: AsyncSession,
    user_id: int,
    direction: str,
    cursor: str,
    page_size: int,
) -> MessageApplicationPage:
    if direction not in {"incoming", "outgoing"}:
        raise HTTPException(422, detail="不支持的申请方向")
    offset, page = _page(cursor, page_size)
    incoming = direction == "incoming"
    source = await discovery.list_applications(db, user_id, incoming, page, page_size)
    peer_ids = [
        int(item.from_user_id if incoming else item.to_user_id) for item in source.items
    ]
    targets = await _target_summaries(db, peer_ids)
    items = [
        _application_item(
            item,
            incoming,
            targets.get(int(item.from_user_id if incoming else item.to_user_id)),
        )
        for item in source.items
    ]
    return MessageApplicationPage(
        list=items,
        next_cursor=str(offset + len(items)) if source.has_more else "",
        has_more=source.has_more,
        total=source.total,
        pending_count=await _incoming_pending_count(db, user_id) if incoming else 0,
    )


async def handle_application(
    db: AsyncSession, user_id: int, application_id: int, action: str, client_command_id: str,
    *, before_mutation: Callable[[], Awaitable[None]] | None = None,
) -> ApplicationHandleResult:
    payload = {"applicationId": application_id, "action": action}
    reservation = await reserve_or_replay(
        db,
        user_id,
        "message.application.handle",
        client_command_id,
        payload,
    )
    try:
        if before_mutation is not None:
            await before_mutation()
        if reservation.response is not None:
            return ApplicationHandleResult.model_validate(reservation.response)
        updated = await discovery.respond_application(
            db,
            user_id,
            application_id,
            action == "accept",
        )
        target = await _target_summaries(db, [int(updated.from_user_id)])
        result = ApplicationHandleResult(
            application=_application_item(updated, True, target.get(int(updated.from_user_id))),
            can_chat=action == "accept",
        )
        await complete(db, reservation, _model_payload(result))
        return result
    except Exception:
        await abort(db, reservation)
        raise


async def get_chat_messages(
    db: AsyncSession, user_id: int, peer_user_id: int
) -> list[MessageChatItem]:
    permission = await get_chat_permission(db, user_id, peer_user_id)
    if not permission.can_chat or permission.session_id is None:
        raise HTTPException(403, detail=permission.reason)
    messages = await social.list_messages(db, user_id, permission.session_id, 1, 50)
    target = await _target_summaries(db, [peer_user_id])
    peer_avatar = target.get(peer_user_id, {}).get("avatar")
    return [
        MessageChatItem(
            id=message.id,
            client_message_id=message.client_message_id,
            type=CHAT_TYPE_NAME.get(message.type, "text"),
            content=message.content or message.media_url or "",
            time=_timestamp(message.created_at),
            is_mine=message.from_user_id == user_id,
            sender_avatar=None if message.from_user_id == user_id else peer_avatar,
            revoked=message.revoked,
        )
        for message in messages
    ]


async def send_chat_message(
    db: AsyncSession, user_id: int, request: MessageSendRequest,
    *, before_mutation: Callable[[], Awaitable[None]] | None = None,
) -> MessageSendResult:
    permission = await get_chat_permission(db, user_id, request.user_id)
    if not permission.can_chat or permission.session_id is None:
        raise HTTPException(403, detail=permission.reason)
    payload = {
        "userId": request.user_id,
        "type": request.type,
        "content": request.content,
        "mediaId": request.media_id,
    }
    reservation = await reserve_or_replay(
        db,
        user_id,
        "message.chat.send",
        request.client_message_id,
        payload,
    )
    try:
        if before_mutation is not None:
            await before_mutation()
            permission = await get_chat_permission(db, user_id, request.user_id)
            if not permission.can_chat or permission.session_id is None:
                raise HTTPException(403, detail=permission.reason)
        if reservation.response is not None:
            return MessageSendResult.model_validate(reservation.response).model_copy(update={"deduplicated": True})
        media_url: str | None = None
        if request.type != "text":
            media = await resolve_owned_ready_media(
                db,
                user_id,
                [int(request.media_id or 0)],
                purpose="chat",
                media_type=request.type,
            )
            media_url = str(media[0]["file_url"])
        created = await social.send_message(
            db,
            user_id,
            permission.session_id,
            ChatMessageCreate(
                type=CHAT_TYPE[request.type],
                content=request.content or None,
                media_url=media_url,
                client_message_id=request.client_message_id,
            ),
            commit=False,
        )
        if request.type != "text":
            await bind_media(
                db,
                media_ids=[int(request.media_id or 0)],
                target_type="chat_message",
                target_id=created.id,
            )
        await db.commit()
        target = await _target_summaries(db, [request.user_id])
        item = MessageChatItem(
            id=created.id,
            client_message_id=created.client_message_id,
            type=request.type,
            content=created.content or created.media_url or "",
            time=_timestamp(created.created_at),
            is_mine=True,
            sender_avatar=target.get(request.user_id, {}).get("avatar"),
            revoked=False,
        )
        result = MessageSendResult(message_id=created.id, message=item)
        await complete(db, reservation, _model_payload(result))
        return result
    except Exception:
        await db.rollback()
        await abort(db, reservation)
        raise


async def revoke_chat_message(
    db: AsyncSession,
    user_id: int,
    message_id: int,
    client_command_id: str,
    *, before_mutation: Callable[[], Awaitable[None]] | None = None,
) -> MessageRevokeResult:
    payload = {"messageId": message_id}
    reservation = await reserve_or_replay(
        db,
        user_id,
        "message.chat.revoke",
        client_command_id,
        payload,
    )
    try:
        if before_mutation is not None:
            await before_mutation()
        if reservation.response is not None:
            return MessageRevokeResult.model_validate(reservation.response)
        await social.revoke_message(db, user_id, message_id)
        result = MessageRevokeResult(message_id=message_id)
        await complete(db, reservation, _model_payload(result))
        return result
    except Exception:
        await abort(db, reservation)
        raise


async def mark_all_messages_read(db: AsyncSession, user_id: int) -> MarkAllReadResult:
    updated_count = await _unread_total(db, user_id)
    if updated_count == 0:
        return MarkAllReadResult(updated_count=0)
    await db.execute(
        text(
            """UPDATE chat_message m
            JOIN chat_session s ON s.id = m.session_id
            SET m.is_read = 1, m.read_at = UTC_TIMESTAMP()
            WHERE m.to_user_id = :user_id AND m.is_read = 0
              AND ((s.user1_id = :user_id AND m.from_user_id = s.user2_id)
                OR (s.user2_id = :user_id AND m.from_user_id = s.user1_id))
              AND EXISTS (
                SELECT 1 FROM user_match um
                WHERE um.user_id = :user_id AND um.target_user_id = m.from_user_id
                  AND um.status IN (1, 2)
              )
              AND NOT EXISTS (
                SELECT 1 FROM user_block ub
                WHERE (ub.user_id = :user_id AND ub.target_user_id = m.from_user_id)
                   OR (ub.user_id = m.from_user_id AND ub.target_user_id = :user_id)
              )"""
        ),
        {"user_id": user_id},
    )
    for side in ("user1", "user2"):
        await db.execute(
            text(
                f"""UPDATE chat_session s SET unread_count_{side} = 0
                WHERE s.{side}_id = :user_id
                  AND EXISTS (
                    SELECT 1 FROM user_match um
                    WHERE um.user_id = :user_id
                      AND um.target_user_id = CASE
                        WHEN s.user1_id = :user_id THEN s.user2_id ELSE s.user1_id END
                      AND um.status IN (1, 2)
                  )"""
            ),
            {"user_id": user_id},
        )
    await db.commit()
    return MarkAllReadResult(updated_count=updated_count)


async def _contact_exchange_row(
    db: AsyncSession, exchange_id: int, user_id: int
) -> tuple[dict[str, Any], int]:
    result = await db.execute(
        text(
            """SELECT * FROM message_contact_exchange
            WHERE id = :exchange_id
              AND (requester_id = :user_id OR recipient_id = :user_id)
            FOR UPDATE"""
        ),
        {"exchange_id": exchange_id, "user_id": user_id},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, detail="联系方式交换请求不存在")
    source = dict(row)
    peer_id = int(source["recipient_id"] if source["requester_id"] == user_id else source["requester_id"])
    permission = await get_chat_permission(db, user_id, peer_id)
    if not permission.can_chat or permission.session_id != int(source["session_id"]):
        raise HTTPException(403, detail="当前没有查看联系方式的权限")
    return source, peer_id


def _contact_exchange_response(row: dict[str, Any], user_id: int) -> ContactExchange:
    accepted = row["status"] == "accepted"
    value: str | None = None
    if accepted:
        try:
            value = decrypt_sensitive(str(row["contact_value_encrypted"]))
        except InvalidToken as exc:
            raise HTTPException(500, detail="联系方式数据无法读取") from exc
    requested_by_me = int(row["requester_id"]) == user_id
    peer_id = int(row["recipient_id"] if requested_by_me else row["requester_id"])
    return ContactExchange(
        id=int(row["id"]),
        user_id=peer_id,
        contact_type=row["contact_type"],
        status=row["status"],
        requested_by_me=requested_by_me,
        contact_value=value,
        created_at=_timestamp(row["created_at"]),
        responded_at=_timestamp(row["responded_at"]) if row["responded_at"] else None,
    )


async def list_contact_exchanges(
    db: AsyncSession, user_id: int, peer_user_id: int
) -> list[ContactExchange]:
    permission = await get_chat_permission(db, user_id, peer_user_id)
    if not permission.can_chat or permission.session_id is None:
        raise HTTPException(403, detail=permission.reason)
    result = await db.execute(
        text(
            """SELECT * FROM message_contact_exchange
            WHERE session_id = :session_id
              AND ((requester_id = :user_id AND recipient_id = :peer_user_id)
                OR (requester_id = :peer_user_id AND recipient_id = :user_id))
            ORDER BY created_at DESC, id DESC
            LIMIT 20"""
        ),
        {
            "session_id": permission.session_id,
            "user_id": user_id,
            "peer_user_id": peer_user_id,
        },
    )
    return [_contact_exchange_response(dict(row), user_id) for row in result.mappings().all()]


async def create_contact_exchange(
    db: AsyncSession, user_id: int, request: ContactExchangeCreateRequest
) -> ContactExchange:
    permission = await get_chat_permission(db, user_id, request.user_id)
    if not permission.can_chat or permission.session_id is None:
        raise HTTPException(403, detail=permission.reason)
    payload = {
        "userId": request.user_id,
        "contactType": request.contact_type,
        "contactValue": request.contact_value,
    }
    reservation = await reserve_or_replay(
        db,
        user_id,
        "message.contact.create",
        request.client_command_id,
        payload,
    )
    if reservation.response is not None:
        return ContactExchange.model_validate(reservation.response)
    try:
        contact_value = request.contact_value
        if request.contact_type == "phone":
            result = await db.execute(
                text("SELECT phone FROM users WHERE id = :user_id"), {"user_id": user_id}
            )
            contact_value = result.scalar()
            if not contact_value:
                raise HTTPException(403, detail="请先绑定手机号后再交换")
        created = await db.execute(
            text(
                """INSERT INTO message_contact_exchange
                (session_id, requester_id, recipient_id, contact_type, contact_value_encrypted)
                VALUES (:session_id, :requester_id, :recipient_id, :contact_type, :contact_value)"""
            ),
            {
                "session_id": permission.session_id,
                "requester_id": user_id,
                "recipient_id": request.user_id,
                "contact_type": request.contact_type,
                "contact_value": encrypt_sensitive(str(contact_value)),
            },
        )
        row_result = await db.execute(
            text("SELECT * FROM message_contact_exchange WHERE id = :id"),
            {"id": created.lastrowid},
        )
        response = _contact_exchange_response(dict(row_result.mappings().one()), user_id)
        await db.commit()
        await complete(db, reservation, _model_payload(response))
        return response
    except Exception:
        await db.rollback()
        await abort(db, reservation)
        raise


async def respond_contact_exchange(
    db: AsyncSession,
    user_id: int,
    exchange_id: int,
    request: ContactExchangeRespondRequest,
) -> ContactExchange:
    payload = {"exchangeId": exchange_id, "action": request.action}
    reservation = await reserve_or_replay(
        db,
        user_id,
        "message.contact.respond",
        request.client_command_id,
        payload,
    )
    if reservation.response is not None:
        return ContactExchange.model_validate(reservation.response)
    try:
        row, _ = await _contact_exchange_row(db, exchange_id, user_id)
        if int(row["recipient_id"]) != user_id:
            raise HTTPException(403, detail="只能处理收到的联系方式交换请求")
        if row["status"] != "pending":
            raise HTTPException(409, detail="联系方式交换请求已处理")
        status = "accepted" if request.action == "accept" else "rejected"
        await db.execute(
            text(
                """UPDATE message_contact_exchange
                SET status = :status, responded_at = UTC_TIMESTAMP()
                WHERE id = :exchange_id AND status = 'pending'"""
            ),
            {"status": status, "exchange_id": exchange_id},
        )
        updated = await db.execute(
            text("SELECT * FROM message_contact_exchange WHERE id = :id"), {"id": exchange_id}
        )
        response = _contact_exchange_response(dict(updated.mappings().one()), user_id)
        await db.commit()
        await complete(db, reservation, _model_payload(response))
        return response
    except Exception:
        await db.rollback()
        await abort(db, reservation)
        raise
