"""Ordinary-user message centre endpoints.

Parent delegation uses the separate /parent routes with verified relationships,
live consent and actor audit records. This router always acts as the logged-in user.
"""

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Path, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_verified_user
from app.db.session import get_db
from app.schemas.community import CommunityMediaResponse
from app.schemas.message import (
    ApplicationHandleRequest,
    ApplicationHandleResult,
    ChatPermissionResponse,
    ContactExchange,
    ContactExchangeCreateRequest,
    ContactExchangePage,
    ContactExchangeRespondRequest,
    MarkAllReadResult,
    MessageApplicationPage,
    MessageChatItem,
    MessageConversationPage,
    MessageRevokeResult,
    MessageSendRequest,
    MessageSendResult,
)
from app.services.community_media import upload_community_media
from app.services.message import (
    create_contact_exchange,
    get_application_page,
    get_chat_messages,
    get_chat_permission,
    get_conversation_page,
    handle_application,
    list_contact_exchanges,
    mark_all_messages_read,
    revoke_chat_message,
    respond_contact_exchange,
    send_chat_message,
)

router = APIRouter(prefix="/message", dependencies=[Depends(get_verified_user)])


@router.get("/list", response_model=MessageConversationPage, summary="消息会话分页")
async def conversation_page(
    cursor: str = Query(default="", max_length=9),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=50),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MessageConversationPage:
    return await get_conversation_page(db, current.id, cursor, page_size)


@router.get("/applications", response_model=MessageApplicationPage, summary="认识申请分页")
async def application_page(
    direction: str = Query(default="incoming", pattern="^(incoming|outgoing)$"),
    cursor: str = Query(default="", max_length=9),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=50),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MessageApplicationPage:
    return await get_application_page(db, current.id, direction, cursor, page_size)


@router.post(
    "/application/handle",
    response_model=ApplicationHandleResult,
    summary="处理收到的认识申请",
)
async def application_handle(
    body: ApplicationHandleRequest = Body(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationHandleResult:
    return await handle_application(
        db,
        current.id,
        body.application_id,
        body.action,
        body.client_command_id,
    )


@router.get("/chat/permission", response_model=ChatPermissionResponse, summary="确认聊天权限")
async def chat_permission(
    user_id: int = Query(alias="userId", ge=1),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ChatPermissionResponse:
    return await get_chat_permission(db, current.id, user_id)


@router.get("/chat", response_model=list[MessageChatItem], summary="读取聊天记录")
async def chat_messages(
    user_id: int = Query(alias="userId", ge=1),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageChatItem]:
    return await get_chat_messages(db, current.id, user_id)


@router.post("/send", response_model=MessageSendResult, summary="发送聊天消息")
async def chat_send(
    body: MessageSendRequest = Body(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MessageSendResult:
    return await send_chat_message(db, current.id, body)


@router.delete(
    "/messages/{message_id}",
    response_model=MessageRevokeResult,
    summary="撤回本人聊天消息",
)
async def chat_revoke(
    message_id: int = Path(..., ge=1),
    client_command_id: str = Query(alias="clientCommandId", min_length=1, max_length=128),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MessageRevokeResult:
    return await revoke_chat_message(db, current.id, message_id, client_command_id)


@router.post("/read-all", response_model=MarkAllReadResult, summary="全部会话标记已读")
async def read_all(
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> MarkAllReadResult:
    return await mark_all_messages_read(db, current.id)


@router.post(
    "/media/uploads",
    response_model=CommunityMediaResponse,
    status_code=201,
    summary="上传聊天媒体",
)
async def media_upload(
    peer_user_id: int = Form(alias="peerUserId", ge=1),
    file: UploadFile = File(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> CommunityMediaResponse:
    permission = await get_chat_permission(db, current.id, peer_user_id)
    if not permission.can_chat:
        raise HTTPException(403, detail=permission.reason)
    return await upload_community_media(db, current.id, file, "chat")


@router.get(
    "/contact-exchanges",
    response_model=ContactExchangePage,
    summary="查看联系方式交换状态",
)
async def contact_exchange_list(
    user_id: int = Query(alias="userId", ge=1),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ContactExchangePage:
    return ContactExchangePage(
        list=await list_contact_exchanges(db, current.id, user_id)
    )


@router.post(
    "/contact-exchanges",
    response_model=ContactExchange,
    summary="发起联系方式交换",
)
async def contact_exchange_create(
    body: ContactExchangeCreateRequest = Body(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ContactExchange:
    return await create_contact_exchange(db, current.id, body)


@router.post(
    "/contact-exchanges/{exchange_id}/respond",
    response_model=ContactExchange,
    summary="确认或拒绝联系方式交换",
)
async def contact_exchange_respond(
    exchange_id: int = Path(..., ge=1),
    body: ContactExchangeRespondRequest = Body(...),
    current: CurrentUser = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
) -> ContactExchange:
    return await respond_contact_exchange(db, current.id, exchange_id, body)
