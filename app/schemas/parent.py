"""Explicit contracts for one-child delegation; no client-supplied actor identity."""
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class ParentModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ParentIdentity(ParentModel):
    id: int = Field(description="资源标识；context 为 parent:父母用户ID，其余资源为数据库整数ID")
    name: str = Field(description="当前账号显示名称")
    avatar: str = Field(default="", description="父母视图固定空字符串，不下发原始头像")
    real_name_status: Literal["missing", "reviewing", "passed", "rejected"] = Field(description="实名状态：missing 未提交、reviewing 审核中、passed 通过、rejected 未通过")


class ParentChild(ParentModel):
    id: int = Field(description="资源标识；context 为 parent:父母用户ID，其余资源为数据库整数ID")
    display_name: str = Field(description="子女或候选的显示称呼")
    birth_year: int = Field(description="已实名认证的出生年份；父母编辑必须与已核验年份完全一致；资料无权访问时为0")
    city: str = Field(description="城市显示名称；编辑时支持唯一城市名称、去市后缀名称或行政编码")
    job: str = Field(description="职业；未公开时返回未公开，编辑时可为空")
    introduction: str = Field(description="已获准展示的自我介绍")
    authorization_status: Literal["pending", "granted", "revoked", "expired"] = Field(description="pending 待授权、granted 当前有效、revoked 已撤销或资格失效、expired 超期")
    authorization_expires_at: str = Field(description="授权到期 UTC ISO 8601 时间；未授予时为空字符串")
    profile_progress: float = Field(description="现有资料完整度分数，范围0至100")


class ParentQuota(ParentModel):
    daily_total: int = Field(default=3, description="父母协助每日申请总额，固定3次，按UTC日期重置")
    remaining_applications: int = Field(ge=0, description="现有子女主体今日剩余次数；包含子女本人发起的申请，不得在客户端猜测扣减")


class ParentReleaseGate(ParentModel):
    production_ready: bool = Field(default=True, description="服务具备关系校验及脱敏能力；不表示当前环境已部署或已通过发布验收")
    code: str = Field(default="OK", description="邀请操作为保密随机邀请码；releaseGate 为服务能力代码；仅服务器存储邀请哈希")
    message: str = Field(default="服务端逐次校验授权并过滤隐私字段", description="服务状态说明或申请附言，取决于对应模型")


class ParentContext(ParentModel):
    id: str = Field(description="资源标识；context 为 parent:父母用户ID，其余资源为数据库整数ID")
    mode: Literal["parent"] = Field(default="parent", description="父母上下文固定为parent")
    data_mode: Literal["http"] = Field(default="http", description="本服务固定http；Mock仅供显式测试模式")
    parent: ParentIdentity = Field(description="当前Token对应父母身份")
    child: ParentChild | None = Field(default=None, description="当前绑定子女及授权状态；未绑定时为null，失效时不下发子女私密资料")
    quota: ParentQuota = Field(description="子女主体的每日申请额度")
    release_gate: ParentReleaseGate = Field(default_factory=ParentReleaseGate, description="后端能力声明")
    message_notifications: bool = Field(default=True, description="父母页内申请与消息提醒开关；不代表操作系统或微信订阅推送")


class ParentInvitation(ParentModel):
    code: str = Field(description="邀请操作为保密随机邀请码；releaseGate 为服务能力代码；仅服务器存储邀请哈希")
    expires_at: str = Field(description="邀请或授权到期UTC ISO 8601时间；未生成时可为空字符串")
    consent_version: str = Field(description="明确授权政策版本parent-consent@1；未知版本拒绝授予或代理操作")


class ParentConsentPreview(ParentModel):
    parent_id: int = Field(description="关系所属父母的用户ID；不得冒用其他账号")
    parent_name: str = Field(description="被授权父母的显示名称")
    consent_version: str = Field(description="明确授权政策版本parent-consent@1；未知版本拒绝授予或代理操作")
    scopes: list[str] = Field(description="子女确认前必须逐项展示的五项授权范围")
    expires_at: str = Field(description="邀请或授权到期UTC ISO 8601时间；未生成时可为空字符串")


class ParentConsentCode(ParentModel):
    code: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$", description="邀请操作为保密随机邀请码；releaseGate 为服务能力代码；仅服务器存储邀请哈希")


class ParentConsentAccept(ParentConsentCode):
    confirmed: Literal[True] = Field(description="子女明确确认；只接受JSON布尔true，拒绝false、1和字符串")
    consent_version: Literal["parent-consent@1"] = Field(default="parent-consent@1", description="明确授权政策版本parent-consent@1；未知版本拒绝授予或代理操作")
    days: int = Field(default=30, ge=1, le=90, strict=True, description="子女确认的授权有效天数，整数1至90，默认30")

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("必须明确确认授权")
        return value


class ParentRelationship(ParentModel):
    parent_id: int = Field(description="关系所属父母的用户ID；不得冒用其他账号")
    parent_name: str = Field(description="被授权父母的显示名称")
    child_id: int | None = Field(description="绑定子女用户ID；尚未绑定时null")
    status: Literal["pending", "granted", "revoked", "expired"] = Field(description="授权状态：pending待授权、granted有效、revoked已撤销、expired已过期")
    expires_at: str = Field(description="邀请或授权到期UTC ISO 8601时间；未生成时可为空字符串")
    consent_version: str = Field(description="明确授权政策版本parent-consent@1；未知版本拒绝授予或代理操作")


class ParentRelationshipPage(ParentModel):
    items: list[ParentRelationship] = Field(description="本页资源数组；无结果为[]，元素结构按引用模型展开")


class ParentChildUpdate(ParentModel):
    display_name: str = Field(min_length=1, max_length=64, description="子女或候选的显示称呼")
    birth_year: int = Field(ge=1940, strict=True, description="已实名认证的出生年份；父母编辑必须与已核验年份完全一致；资料无权访问时为0")
    city: str = Field(min_length=1, max_length=64, description="城市显示名称；编辑时支持唯一城市名称、去市后缀名称或行政编码")
    job: str = Field(default="", max_length=128, description="职业；未公开时返回未公开，编辑时可为空")
    introduction: str = Field(default="", max_length=1000, description="已获准展示的自我介绍")

    @field_validator("birth_year")
    @classmethod
    def adult_year(cls, value):
        if value > datetime.now(UTC).year - 18:
            raise ValueError("子女必须成年")
        return value

    @field_validator("display_name", "city", "job", "introduction")
    @classmethod
    def trim(cls, value):
        return value.strip()


class ParentPreference(ParentModel):
    message_notifications: bool = Field(default=True, description="父母页内申请与消息提醒开关；不代表操作系统或微信订阅推送")
    allow_parent_photo: bool = Field(default=False, description="当前账号本人许可父母视图看清晰照片；默认关闭，仅详情可使用，列表和聊天始终脱敏")


class ParentPreferenceUpdate(ParentModel):
    message_notifications: bool | None = Field(default=None, description="父母页内申请与消息提醒开关；不代表操作系统或微信订阅推送")
    allow_parent_photo: bool | None = Field(default=None, description="当前账号本人许可父母视图看清晰照片；默认关闭，仅详情可使用，列表和聊天始终脱敏")


class ParentCandidate(ParentModel):
    id: int = Field(description="资源标识；context 为 parent:父母用户ID，其余资源为数据库整数ID")
    display_name: str = Field(description="子女或候选的显示称呼")
    gender_text: str = Field(description="男、女或未公开")
    birth_year: int = Field(description="已实名认证的出生年份；父母编辑必须与已核验年份完全一致；资料无权访问时为0")
    city: str = Field(description="城市显示名称；编辑时支持唯一城市名称、去市后缀名称或行政编码")
    height: str = Field(description="带cm单位的身高显示值；受隐私限制时为未公开")
    education: str = Field(description="学历显示名称；遵循数据库学历编码及本人隐私设置")
    job: str = Field(description="职业；未公开时返回未公开，编辑时可为空")
    income: str = Field(default="未公开", description="父母视图当前固定未公开")
    certification_text: str = Field(description="根据真实认证信息生成的展示标签")
    avatar: str = Field(default="", description="父母视图固定空字符串，不下发原始头像")
    clear_avatar: str = Field(default="", description="仅候选本人许可且详情可见时下发清晰头像URL，其他情形为空")
    introduction: str = Field(default="", description="已获准展示的自我介绍")
    dating_notes: str = Field(default="是否继续由双方本人决定。", description="认识与沟通边界说明")
    expectations: list[str] = Field(default_factory=list, description="公开期待列表，未提供时[]")
    liked: bool = Field(default=False, description="该候选在子女主体下的私密喜欢状态；不通知对方")
    can_view_clear_photo: bool = Field(default=False, description="当前详情是否获准下发清晰照片；列表始终false")


class ParentCandidatePage(ParentModel):
    items: list[ParentCandidate] = Field(description="本页资源数组；无结果为[]，元素结构按引用模型展开")
    page: int = Field(description="当前页，从1开始")
    page_size: int = Field(description="每页条数，默认20，父母候选最多20")
    total: int = Field(description="满足可见性条件的总条数")
    has_more: bool = Field(description="是否还有下一页")


class ParentApplyRequest(ParentModel):
    note: str = Field(min_length=1, max_length=120, description="认识申请附言，去首尾空白后不可为空；相同待回应申请的重试必须相同")

    @field_validator("note")
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError("申请说明不能为空")
        return value.strip()


class ParentApplyResult(ParentModel):
    success: Literal[True] = Field(default=True, description="业务操作成功，固定true；失败使用HTTP错误状态")
    application_id: int = Field(description="现有match_apply申请记录ID")
    apply_status: Literal["pending"] = Field(default="pending", description="发出认识申请后固定pending，聊天仍需对方接受")
    remaining_applications: int = Field(description="现有子女主体今日剩余次数；包含子女本人发起的申请，不得在客户端猜测扣减")
    deduplicated: bool = Field(default=False, description="是否复用已有同内容待回应申请")


class ParentLikeRequest(ParentModel):
    liked: bool = Field(description="该候选在子女主体下的私密喜欢状态；不通知对方")


class ParentLikeResult(ParentModel):
    success: Literal[True] = Field(default=True, description="业务操作成功，固定true；失败使用HTTP错误状态")
    user_id: int = Field(description="目标候选用户ID")
    liked: bool = Field(description="该候选在子女主体下的私密喜欢状态；不通知对方")


class ParentReportRequest(ParentModel):
    reason_id: str = Field(min_length=1, max_length=64, description="举报原因，复用现有安全举报类型；other表示其他")
    detail: str = Field(default="", max_length=1000, description="举报补充描述，可为空")


class ParentSuccess(ParentModel):
    success: Literal[True] = Field(default=True, description="业务操作成功，固定true；失败使用HTTP错误状态")


class ParentAlerts(ParentModel):
    enabled: bool = Field(description="页内提醒当前是否开启")
    latest_event_id: int = Field(default=0, description="当前子女申请与消息提醒事件最大ID，仅作变化标记；无事件为0")
    unread_count: int = Field(default=0, description="当前可见会话未读总数")
    pending_count: int = Field(default=0, description="子女收到的待回应申请数量")
