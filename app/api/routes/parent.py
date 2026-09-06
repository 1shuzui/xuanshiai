"""Authenticated parent routes. All delegated resources carry a verified child path."""
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_verified_user
from app.db.session import get_db
from app.schemas import parent as schema
from app.schemas.message import (ApplicationHandleRequest, ApplicationHandleResult, ChatPermissionResponse,
    MarkAllReadResult, MessageApplicationPage, MessageChatItem, MessageConversationPage,
    MessageRevokeResult, MessageSendRequest, MessageSendResult)
from app.schemas.social import ReportResponse
from app.services import message, parent

router = APIRouter(prefix="/parent", dependencies=[Depends(get_verified_user)])


def _command_key(parent_id: int, client_key: str) -> str:
    """Separate actors without exceeding the shared 128-character storage limit."""
    return f"p{parent_id}:" + hashlib.sha256(client_key.encode()).hexdigest()


@router.get("/context", response_model=schema.ParentContext, summary="当前父母身份及有效子女授权")
async def context(current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.get_context(db, current)


@router.post("/invitations", response_model=schema.ParentInvitation, status_code=201, summary="父母生成有效期24小时的邀请")
async def invite(current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.create_invitation(db, current)


@router.post("/invitations/preview", response_model=schema.ParentConsentPreview, summary="子女预览邀请方与授权范围")
async def preview(body: schema.ParentConsentCode, current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.preview_invitation(db, current, body)


@router.post("/invitations/accept", response_model=schema.ParentRelationship, summary="成年子女明确确认授权")
async def accept(body: schema.ParentConsentAccept, current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.accept_invitation(db, current, body)


@router.get("/relationships", response_model=schema.ParentRelationshipPage, summary="本人关联的父母授权记录")
async def relationships(current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.relationship_page(db, current)


@router.delete("/relationships/{parent_id}", response_model=schema.ParentSuccess, summary="父母或子女撤销授权")
async def revoke(parent_id: int = Path(ge=1), current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.revoke_relationship(db, current, parent_id)


@router.get("/preferences", response_model=schema.ParentPreference, summary="父母提醒与本人照片许可")
async def preferences(current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.preferences(db, current.id)


@router.patch("/preferences", response_model=schema.ParentPreference, summary="修改父母提醒或本人照片许可")
async def set_preferences(body: schema.ParentPreferenceUpdate, current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.update_preferences(db, current, body)


@router.put("/children/{child_id}", response_model=schema.ParentChild, summary="代子女完善允许编辑的资料")
async def update_child(body: schema.ParentChildUpdate, child_id: int = Path(ge=1), current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.update_child(db, current, child_id, body)


@router.get("/children/{child_id}/candidates", response_model=schema.ParentCandidatePage, summary="子女主体推荐及喜欢列表")
async def candidates(child_id: int = Path(ge=1), page: int = Query(1, ge=1, le=1000), page_size: int = Query(20, alias="pageSize", ge=1, le=20),
                     liked: bool = False, current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.candidates(db, current, child_id, page, page_size, liked)


@router.get("/children/{child_id}/candidates/{target_id}", response_model=schema.ParentCandidate, summary="隐私保护的父母候选详情")
async def detail(child_id: int = Path(ge=1), target_id: int = Path(ge=1), current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.candidate_detail(db, current, child_id, target_id)


@router.put("/children/{child_id}/likes/{target_id}", response_model=schema.ParentLikeResult, summary="设置子女主体的私密喜欢状态")
async def like(body: schema.ParentLikeRequest, child_id: int = Path(ge=1), target_id: int = Path(ge=1),
               current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.set_like(db, current, child_id, target_id, body)


@router.post("/children/{child_id}/applications/{target_id}", response_model=schema.ParentApplyResult, summary="代子女发出幂等认识申请")
async def apply(body: schema.ParentApplyRequest, child_id: int = Path(ge=1), target_id: int = Path(ge=1),
                current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.create_application(db, current, child_id, target_id, body)


@router.put("/children/{child_id}/blocks/{target_id}", response_model=schema.ParentSuccess, summary="屏蔽子女主体候选")
async def block(child_id: int = Path(ge=1), target_id: int = Path(ge=1), current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.block_candidate(db, current, child_id, target_id)


@router.post("/children/{child_id}/reports/{target_id}", response_model=ReportResponse, summary="父母实名主体提交安全举报")
async def report(body: schema.ParentReportRequest, child_id: int = Path(ge=1), target_id: int = Path(ge=1),
                 current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.report_candidate(db, current, child_id, target_id, body)


@router.get("/children/{child_id}/message/list", response_model=MessageConversationPage, summary="父母查看已获同意的子女会话")
async def conversations(child_id: int = Path(ge=1), cursor: str = Query("", max_length=9), page_size: int = Query(20, alias="pageSize", ge=1, le=50),
                        current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    await parent.authorize_parent(db, current, child_id)
    return parent.protect_parent_payload(await message.get_conversation_page(db, child_id, cursor, page_size))


@router.get("/children/{child_id}/message/applications", response_model=MessageApplicationPage, summary="父母查看子女申请分页")
async def applications(child_id: int = Path(ge=1), direction: str = Query("incoming", pattern="^(incoming|outgoing)$"),
                       cursor: str = Query("", max_length=9), page_size: int = Query(20, alias="pageSize", ge=1, le=50),
                       current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    await parent.authorize_parent(db, current, child_id)
    return parent.protect_parent_payload(await message.get_application_page(db, child_id, direction, cursor, page_size))


@router.get("/children/{child_id}/message/chat/permission", response_model=ChatPermissionResponse, summary="父母聊天前核验双方同意")
async def permission(child_id: int = Path(ge=1), user_id: int = Query(alias="userId", ge=1),
                     current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    await parent.authorize_parent(db, current, child_id)
    return await message.get_chat_permission(db, child_id, user_id)


@router.get("/children/{child_id}/message/chat", response_model=list[MessageChatItem], summary="父母读取脱敏聊天记录")
async def chat(child_id: int = Path(ge=1), user_id: int = Query(alias="userId", ge=1),
               current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    await parent.authorize_parent(db, current, child_id)
    return parent.protect_parent_payload(await message.get_chat_messages(db, child_id, user_id))


@router.post("/children/{child_id}/message/send", response_model=MessageSendResult, summary="父母发送已获授权的文字消息")
async def send(body: MessageSendRequest, child_id: int = Path(ge=1), current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    await parent.authorize_parent(db, current, child_id)
    if body.type != "text" or body.media_id is not None:
        raise HTTPException(403, detail="父母端仅支持已同意认识后的文字聊天")
    client_key = body.client_message_id
    body = body.model_copy(update={"client_message_id": _command_key(current.id, client_key)})
    async def guard():
        await parent.message_guard(db, current, child_id, "message.send_attempt", body.user_id)
    result = parent.protect_parent_payload(await message.send_chat_message(db, child_id, body, before_mutation=guard))
    result["message"]["clientMessageId"] = client_key
    return result


@router.post("/children/{child_id}/message/application/handle", response_model=ApplicationHandleResult, summary="父母处理子女收到的申请")
async def handle(body: ApplicationHandleRequest, child_id: int = Path(ge=1), current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    await parent.authorize_parent(db, current, child_id)
    async def guard():
        await parent.message_guard(db, current, child_id, "application." + body.action + "_attempt")
    return parent.protect_parent_payload(await message.handle_application(db, child_id, body.application_id,
        body.action, _command_key(current.id, body.client_command_id), before_mutation=guard))


@router.post("/children/{child_id}/message/read-all", response_model=MarkAllReadResult, summary="父母标记子女会话已读")
async def read_all(child_id: int = Path(ge=1), current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    await parent.message_guard(db, current, child_id, "message.read")
    return await message.mark_all_messages_read(db, child_id)


@router.delete("/children/{child_id}/message/messages/{message_id}", response_model=MessageRevokeResult, summary="父母撤回授权主体发出的消息")
async def revoke_message(child_id: int = Path(ge=1), message_id: int = Path(ge=1), client_command_id: str = Query(alias="clientCommandId", min_length=1, max_length=100),
                         current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    await parent.authorize_parent(db, current, child_id)
    async def guard():
        await parent.message_guard(db, current, child_id, "message.revoke_attempt")
    return await message.revoke_chat_message(db, child_id, message_id, _command_key(current.id, client_command_id), before_mutation=guard)


@router.get("/children/{child_id}/alerts", response_model=schema.ParentAlerts, summary="有效授权下的页内提醒摘要")
async def alerts(child_id: int = Path(ge=1), current: CurrentUser = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    return await parent.alerts(db, current, child_id)
