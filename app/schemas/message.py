"""Public contracts for the ordinary-user message centre facade."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.auth import MbtiType


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class MessageConversation(CamelModel):
    id: int
    conversation_id: str = Field(alias="conversationId")
    user_id: int = Field(alias="userId")
    avatar: str | None
    name: str
    last_message: str = Field(alias="lastMessage")
    time: int
    unread_count: int = Field(alias="unreadCount", ge=0)
    online: bool = False
    message_type: Literal["text", "image", "voice", "video"] = Field(
        default="text", alias="messageType"
    )
    type: Literal["chat"] = "chat"
    matched: bool = True
    can_chat: bool = Field(default=True, alias="canChat")


class MessageConversationPage(CamelModel):
    list: list[MessageConversation]
    next_cursor: str = Field(alias="nextCursor")
    has_more: bool = Field(alias="hasMore")
    total: int = Field(ge=0)
    unread_total: int = Field(alias="unreadTotal", ge=0)


class MessageApplication(CamelModel):
    id: int
    user_id: int = Field(alias="userId")
    avatar: str | None
    name: str
    message: str
    time: int
    status: Literal["pending", "accepted", "rejected", "expired"]
    status_text: str = Field(alias="statusText")
    direction: Literal["in", "out"]


class MessageApplicationPage(CamelModel):
    list: list[MessageApplication]
    next_cursor: str = Field(alias="nextCursor")
    has_more: bool = Field(alias="hasMore")
    total: int = Field(ge=0)
    pending_count: int = Field(default=0, alias="pendingCount", ge=0)


class ChatPermissionResponse(CamelModel):
    user_id: int = Field(alias="userId")
    conversation_id: str = Field(default="", alias="conversationId")
    session_id: int | None = Field(default=None, alias="sessionId")
    can_chat: bool = Field(alias="canChat")
    reason: str


class MessageChatItem(CamelModel):
    id: int
    client_message_id: str | None = Field(default=None, alias="clientMessageId")
    type: Literal["text", "image", "voice", "video"]
    content: str
    time: int
    is_mine: bool = Field(alias="isMine")
    sender_avatar: str | None = Field(default=None, alias="senderAvatar")
    revoked: bool = False


class MessageSendRequest(CamelModel):
    user_id: int = Field(alias="userId", ge=1)
    content: str = Field(default="", max_length=5000)
    type: Literal["text", "image", "voice", "video"] = "text"
    client_message_id: str = Field(alias="clientMessageId", min_length=1, max_length=128)
    media_id: int | None = Field(default=None, alias="mediaId", ge=1)

    @field_validator("content")
    @classmethod
    def trim_content(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_payload(self) -> "MessageSendRequest":
        if self.type == "text" and not self.content:
            raise ValueError("文本消息内容不能为空")
        if self.type != "text" and self.media_id is None:
            raise ValueError("媒体消息必须引用已上传媒体")
        if self.type != "text" and self.content:
            raise ValueError("媒体消息不能同时附带文本内容")
        return self


class MessageSendResult(CamelModel):
    success: Literal[True] = True
    message_id: int = Field(alias="messageId")
    message: MessageChatItem
    deduplicated: bool = False


class MessageRevokeResult(CamelModel):
    success: Literal[True] = True
    message_id: int = Field(alias="messageId")


class ApplicationHandleRequest(CamelModel):
    application_id: int = Field(alias="applicationId", ge=1)
    action: Literal["accept", "reject"]
    client_command_id: str = Field(alias="clientCommandId", min_length=1, max_length=128)


class ApplicationHandleResult(CamelModel):
    success: Literal[True] = True
    application: MessageApplication
    can_chat: bool = Field(alias="canChat")


class MarkAllReadResult(CamelModel):
    success: Literal[True] = True
    updated_count: int = Field(alias="updatedCount", ge=0)
    unread_total: Literal[0] = Field(default=0, alias="unreadTotal")


class ContactExchangeCreateRequest(CamelModel):
    user_id: int = Field(alias="userId", ge=1)
    contact_type: Literal["phone", "wechat"] = Field(alias="contactType")
    contact_value: str | None = Field(default=None, alias="contactValue", max_length=64)
    client_command_id: str = Field(alias="clientCommandId", min_length=1, max_length=128)

    @field_validator("contact_value")
    @classmethod
    def normalize_contact_value(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_contact_value(self) -> "ContactExchangeCreateRequest":
        if self.contact_type == "wechat":
            if not self.contact_value or len(self.contact_value) < 6:
                raise ValueError("请填写有效微信号")
        elif self.contact_value:
            raise ValueError("手机号仅可交换当前账号已验证手机号")
        return self


class ContactExchangeRespondRequest(CamelModel):
    action: Literal["accept", "reject"]
    client_command_id: str = Field(alias="clientCommandId", min_length=1, max_length=128)


class ContactExchange(CamelModel):
    id: int
    user_id: int = Field(alias="userId")
    contact_type: Literal["phone", "wechat"] = Field(alias="contactType")
    status: Literal["pending", "accepted", "rejected"]
    requested_by_me: bool = Field(alias="requestedByMe")
    contact_value: str | None = Field(default=None, alias="contactValue")
    created_at: int = Field(alias="createdAt")
    responded_at: int | None = Field(default=None, alias="respondedAt")


class ContactExchangePage(CamelModel):
    list: list[ContactExchange]


class EmotionAssessmentDefinition(CamelModel):
    id: str
    version: str
    kind: Literal["mbti"] = "mbti"
    title: str
    authorization: dict[str, str | int | None]
    can_start: bool = Field(alias="canStart")
    question_count: int = Field(alias="questionCount", ge=0)
    scale: dict[str, int]
    dimensions: list[str]
    tie_break: Literal["first_pole"] = Field(alias="tieBreak")
    result_copy_version: str = Field(alias="resultCopyVersion")


class EmotionQuestionOption(CamelModel):
    value: int = Field(ge=1, le=7)
    label: str = Field(min_length=1, max_length=32)


class EmotionQuestionSnapshot(CamelModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=500)
    options: list[EmotionQuestionOption] = Field(min_length=2, max_length=7)


class MbtiAnswer(CamelModel):
    question_id: str = Field(alias="questionId", min_length=1, max_length=128)
    value: int = Field(ge=1, le=7)


class MbtiResultCopy(CamelModel):
    version: str
    title: str
    summary: str
    disclaimer: str


class MbtiResult(CamelModel):
    id: str
    session_id: str = Field(alias="sessionId")
    assessment_id: str = Field(alias="assessmentId")
    assessment_version: str = Field(alias="assessmentVersion")
    source: Literal["assessment"] = "assessment"
    mbti_type: MbtiType = Field(alias="mbtiType")
    dimensions: dict[str, dict[str, int]]
    result_copy: MbtiResultCopy = Field(alias="resultCopy")
    completed_at: int = Field(alias="completedAt")


class EmotionSessionSnapshot(CamelModel):
    schema_version: Literal[2] = Field(alias="schemaVersion")
    id: str
    definition_id: str = Field(alias="definitionId")
    definition_version: str = Field(alias="definitionVersion")
    result_copy_version: str = Field(alias="resultCopyVersion")
    kind: Literal["mbti"] = "mbti"
    status: Literal["in_progress", "completed", "discarded"]
    question_ids: list[str] = Field(alias="questionIds")
    questions: list[EmotionQuestionSnapshot]
    answers: list[MbtiAnswer]
    result: MbtiResult | None = None
    created_at: int = Field(alias="createdAt")
    updated_at: int = Field(alias="updatedAt")


class EmotionProfileSource(CamelModel):
    mbti_type: MbtiType = Field(alias="mbtiType")
    source: Literal["assessment", "self_reported"]
    assessment_version: str | None = Field(default=None, alias="assessmentVersion")
    result_id: str | None = Field(default=None, alias="resultId")
    confirmed_at: int = Field(alias="confirmedAt")


class EmotionLabSummary(CamelModel):
    assessments: list[EmotionAssessmentDefinition]
    manual_types: list[MbtiType] = Field(alias="manualTypes")
    active_session: EmotionSessionSnapshot | None = Field(
        default=None, alias="activeSession"
    )
    profile_source: EmotionProfileSource | None = Field(default=None, alias="profileSource")
    disclaimer: str
    disclaimer_version: str = Field(alias="disclaimerVersion")


class EmotionProfileSourceUpdate(CamelModel):
    mbti_type: MbtiType = Field(alias="mbtiType")
    source: Literal["assessment", "self_reported"]
    confirmed: bool
    result_id: str | None = Field(default=None, alias="resultId", max_length=128)


class EmotionSessionCreate(CamelModel):
    assessment_id: str = Field(default="mbti-core", alias="assessmentId", min_length=1, max_length=64)


class EmotionAnswersUpdate(CamelModel):
    answers: list[MbtiAnswer] = Field(min_length=1, max_length=100)
