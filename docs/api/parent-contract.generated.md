# 父母端逐字段契约（自动生成）

由 `python scripts/export_parent_api_docs.py` 从实际 OpenAPI 生成。业务权限、状态与迁移见 [父母端接口](parent.md)。

所有请求使用 `Authorization: Bearer <access_token>`；有 JSON 请求体时使用 `Content-Type: application/json`。成功响应也是 JSON，直接返回业务对象。

请求模型的“必填”指客户端输入；响应模型的字段均按 response_model 返回，nullable 字段可为 null。默认空字符串表示未公开或未填写；空数组表示当前没有记录。所有嵌套类型均在下方展开。

## GET /api/v1/parent/context

当前父母身份及有效子女授权

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |

```http
GET /api/v1/parent/context
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ParentContext`。结构示例（空列表为合法空态）：

```json
{
  "id": "parent:101",
  "mode": "parent",
  "dataMode": "http",
  "parent": {
    "id": 101,
    "name": "家人",
    "avatar": "",
    "realNameStatus": "missing"
  },
  "child": null,
  "quota": {
    "dailyTotal": 3,
    "remainingApplications": 3
  },
  "releaseGate": {
    "productionReady": true,
    "code": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "message": "服务端逐次校验授权并过滤隐私字段"
  },
  "messageNotifications": true
}
```

## POST /api/v1/parent/invitations

父母生成有效期24小时的邀请

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |

```http
POST /api/v1/parent/invitations
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `201`；返回 `ParentInvitation`。结构示例（空列表为合法空态）：

```json
{
  "code": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expiresAt": "2026-10-06T00:00:00.000Z",
  "consentVersion": "parent-consent@1"
}
```

## POST /api/v1/parent/invitations/preview

子女预览邀请方与授权范围

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |

```http
POST /api/v1/parent/invitations/preview
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "code": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

请求体：`ParentConsentCode`，字段约束见下方对应模型。

成功状态 `200`；返回 `ParentConsentPreview`。结构示例（空列表为合法空态）：

```json
{
  "parentId": 101,
  "parentName": "示例",
  "consentVersion": "parent-consent@1",
  "scopes": [
    "完善资料",
    "查看推荐",
    "私密喜欢",
    "处理申请",
    "同意后文字聊天"
  ],
  "expiresAt": "2026-10-06T00:00:00.000Z"
}
```

## POST /api/v1/parent/invitations/accept

成年子女明确确认授权

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |

```http
POST /api/v1/parent/invitations/accept
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "code": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "confirmed": true,
  "consentVersion": "parent-consent@1",
  "days": 30
}
```

请求体：`ParentConsentAccept`，字段约束见下方对应模型。

成功状态 `200`；返回 `ParentRelationship`。结构示例（空列表为合法空态）：

```json
{
  "parentId": 101,
  "parentName": "示例",
  "childId": 202,
  "status": "pending",
  "expiresAt": "2026-10-06T00:00:00.000Z",
  "consentVersion": "parent-consent@1"
}
```

## GET /api/v1/parent/relationships

本人关联的父母授权记录

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |

```http
GET /api/v1/parent/relationships
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ParentRelationshipPage`。结构示例（空列表为合法空态）：

```json
{
  "items": []
}
```

## DELETE /api/v1/parent/relationships/{parent_id}

父母或子女撤销授权

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `parent_id` | path | integer | 是 | minimum=1 | Parent Id |

```http
DELETE /api/v1/parent/relationships/101
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ParentSuccess`。结构示例（空列表为合法空态）：

```json
{
  "success": true
}
```

## GET /api/v1/parent/preferences

父母提醒与本人照片许可

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |

```http
GET /api/v1/parent/preferences
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ParentPreference`。结构示例（空列表为合法空态）：

```json
{
  "messageNotifications": true,
  "allowParentPhoto": false
}
```

## PATCH /api/v1/parent/preferences

修改父母提醒或本人照片许可

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |

```http
PATCH /api/v1/parent/preferences
Authorization: Bearer <access_token>
Content-Type: application/json

{}
```

请求体：`ParentPreferenceUpdate`，字段约束见下方对应模型。

成功状态 `200`；返回 `ParentPreference`。结构示例（空列表为合法空态）：

```json
{
  "messageNotifications": true,
  "allowParentPhoto": false
}
```

## PUT /api/v1/parent/children/{child_id}

代子女完善允许编辑的资料

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |

```http
PUT /api/v1/parent/children/202
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "displayName": "家人",
  "birthYear": 1996,
  "city": "南京",
  "job": "工程师",
  "introduction": ""
}
```

请求体：`ParentChildUpdate`，字段约束见下方对应模型。

成功状态 `200`；返回 `ParentChild`。结构示例（空列表为合法空态）：

```json
{
  "id": 101,
  "displayName": "家人",
  "birthYear": 1996,
  "city": "南京",
  "job": "工程师",
  "introduction": "示例",
  "authorizationStatus": "pending",
  "authorizationExpiresAt": "2026-10-06T00:00:00.000Z",
  "profileProgress": 0
}
```

## GET /api/v1/parent/children/{child_id}/candidates

子女主体推荐及喜欢列表

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `page` | query | integer | 否 | default=1; minimum=1; maximum=1000 | Page |
| `pageSize` | query | integer | 否 | default=20; minimum=1; maximum=20 | Pagesize |
| `liked` | query | boolean | 否 | default=false | Liked |

```http
GET /api/v1/parent/children/202/candidates?page=1&pageSize=20
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ParentCandidatePage`。结构示例（空列表为合法空态）：

```json
{
  "items": [],
  "page": 1,
  "pageSize": 20,
  "total": 0,
  "hasMore": false
}
```

## GET /api/v1/parent/children/{child_id}/candidates/{target_id}

隐私保护的父母候选详情

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `target_id` | path | integer | 是 | minimum=1 | Target Id |

```http
GET /api/v1/parent/children/202/candidates/303
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ParentCandidate`。结构示例（空列表为合法空态）：

```json
{
  "id": 101,
  "displayName": "家人",
  "genderText": "示例",
  "birthYear": 1996,
  "city": "南京",
  "height": "示例",
  "education": "示例",
  "job": "工程师",
  "income": "未公开",
  "certificationText": "示例",
  "avatar": "",
  "clearAvatar": "",
  "introduction": "",
  "datingNotes": "是否继续由双方本人决定。",
  "expectations": [],
  "liked": false,
  "canViewClearPhoto": false
}
```

## PUT /api/v1/parent/children/{child_id}/likes/{target_id}

设置子女主体的私密喜欢状态

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `target_id` | path | integer | 是 | minimum=1 | Target Id |

```http
PUT /api/v1/parent/children/202/likes/303
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "liked": false
}
```

请求体：`ParentLikeRequest`，字段约束见下方对应模型。

成功状态 `200`；返回 `ParentLikeResult`。结构示例（空列表为合法空态）：

```json
{
  "success": true,
  "userId": 303,
  "liked": false
}
```

## POST /api/v1/parent/children/{child_id}/applications/{target_id}

代子女发出幂等认识申请

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `target_id` | path | integer | 是 | minimum=1 | Target Id |

```http
POST /api/v1/parent/children/202/applications/303
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "note": "希望认真了解"
}
```

请求体：`ParentApplyRequest`，字段约束见下方对应模型。

成功状态 `200`；返回 `ParentApplyResult`。结构示例（空列表为合法空态）：

```json
{
  "success": true,
  "applicationId": 301,
  "applyStatus": "pending",
  "remainingApplications": 3,
  "deduplicated": false
}
```

## PUT /api/v1/parent/children/{child_id}/blocks/{target_id}

屏蔽子女主体候选

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `target_id` | path | integer | 是 | minimum=1 | Target Id |

```http
PUT /api/v1/parent/children/202/blocks/303
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ParentSuccess`。结构示例（空列表为合法空态）：

```json
{
  "success": true
}
```

## POST /api/v1/parent/children/{child_id}/reports/{target_id}

父母实名主体提交安全举报

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `target_id` | path | integer | 是 | minimum=1 | Target Id |

```http
POST /api/v1/parent/children/202/reports/303
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "reasonId": "other",
  "detail": "说明具体情况"
}
```

请求体：`ParentReportRequest`，字段约束见下方对应模型。

成功状态 `200`；返回 `ReportResponse`。结构示例（空列表为合法空态）：

```json
{
  "id": 101,
  "target_user_id": 0,
  "target_type": "user",
  "target_id": 303,
  "type": "示例",
  "status": 0,
  "created_at": "示例"
}
```

## GET /api/v1/parent/children/{child_id}/message/list

父母查看已获同意的子女会话

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `cursor` | query | string | 否 | default=""; maxLength=9 | Cursor |
| `pageSize` | query | integer | 否 | default=20; minimum=1; maximum=50 | Pagesize |

```http
GET /api/v1/parent/children/202/message/list?cursor=&pageSize=20
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `MessageConversationPage`。结构示例（空列表为合法空态）：

```json
{
  "list": [],
  "nextCursor": "示例",
  "hasMore": false,
  "total": 0,
  "unreadTotal": 0.0
}
```

## GET /api/v1/parent/children/{child_id}/message/applications

父母查看子女申请分页

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `direction` | query | string | 否 | default="incoming"; pattern="^(incoming|outgoing)$" | Direction |
| `cursor` | query | string | 否 | default=""; maxLength=9 | Cursor |
| `pageSize` | query | integer | 否 | default=20; minimum=1; maximum=50 | Pagesize |

```http
GET /api/v1/parent/children/202/message/applications?cursor=&pageSize=20
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `MessageApplicationPage`。结构示例（空列表为合法空态）：

```json
{
  "list": [],
  "nextCursor": "示例",
  "hasMore": false,
  "total": 0,
  "pendingCount": 0
}
```

## GET /api/v1/parent/children/{child_id}/message/chat/permission

父母聊天前核验双方同意

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `userId` | query | integer | 是 | minimum=1 | Userid |

```http
GET /api/v1/parent/children/202/message/chat/permission?userId=303
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ChatPermissionResponse`。结构示例（空列表为合法空态）：

```json
{
  "userId": 303,
  "conversationId": "",
  "sessionId": null,
  "canChat": false,
  "reason": "示例"
}
```

## GET /api/v1/parent/children/{child_id}/message/chat

父母读取脱敏聊天记录

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `userId` | query | integer | 是 | minimum=1 | Userid |

```http
GET /api/v1/parent/children/202/message/chat?userId=303
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `array[MessageChatItem]`。结构示例（空列表为合法空态）：

```json
[]
```

## POST /api/v1/parent/children/{child_id}/message/send

父母发送已获授权的文字消息

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |

```http
POST /api/v1/parent/children/202/message/send
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "userId": 303,
  "content": "你好，想认真了解彼此",
  "type": "text",
  "clientMessageId": "send-20260906-1"
}
```

请求体：`MessageSendRequest`，字段约束见下方对应模型。

成功状态 `200`；返回 `MessageSendResult`。结构示例（空列表为合法空态）：

```json
{
  "success": true,
  "messageId": 0,
  "message": {
    "id": 101,
    "clientMessageId": "send-20260906-1",
    "type": "text",
    "content": "你好，想认真了解彼此",
    "time": 1788652800000,
    "isMine": false,
    "senderAvatar": null,
    "revoked": false
  },
  "deduplicated": false
}
```

## POST /api/v1/parent/children/{child_id}/message/application/handle

父母处理子女收到的申请

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |

```http
POST /api/v1/parent/children/202/message/application/handle
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "applicationId": 301,
  "action": "accept",
  "clientCommandId": "command-20260906-1"
}
```

请求体：`ApplicationHandleRequest`，字段约束见下方对应模型。

成功状态 `200`；返回 `ApplicationHandleResult`。结构示例（空列表为合法空态）：

```json
{
  "success": true,
  "application": {
    "id": 101,
    "userId": 303,
    "avatar": null,
    "name": "家人",
    "message": "示例",
    "time": 1788652800000,
    "status": "pending",
    "statusText": "示例",
    "direction": "in"
  },
  "canChat": false
}
```

## POST /api/v1/parent/children/{child_id}/message/read-all

父母标记子女会话已读

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |

```http
POST /api/v1/parent/children/202/message/read-all
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `MarkAllReadResult`。结构示例（空列表为合法空态）：

```json
{
  "success": true,
  "updatedCount": 0.0,
  "unreadTotal": 0
}
```

## DELETE /api/v1/parent/children/{child_id}/message/messages/{message_id}

父母撤回授权主体发出的消息

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |
| `message_id` | path | integer | 是 | minimum=1 | Message Id |
| `clientCommandId` | query | string | 是 | minLength=1; maxLength=100 | Clientcommandid |

```http
DELETE /api/v1/parent/children/202/message/messages/501?clientCommandId=command-20260906-1
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `MessageRevokeResult`。结构示例（空列表为合法空态）：

```json
{
  "success": true,
  "messageId": 0
}
```

## GET /api/v1/parent/children/{child_id}/alerts

有效授权下的页内提醒摘要

| 参数 | 位置 | JSON 类型 | 必填 | 默认与约束 | 含义 |
| --- | --- | --- | --- | --- | --- |
| `child_id` | path | integer | 是 | minimum=1 | Child Id |

```http
GET /api/v1/parent/children/202/alerts
Authorization: Bearer <access_token>
```

无请求体。

成功状态 `200`；返回 `ParentAlerts`。结构示例（空列表为合法空态）：

```json
{
  "enabled": false,
  "latestEventId": 0,
  "unreadCount": 0,
  "pendingCount": 0
}
```

## ApplicationHandleRequest

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `applicationId` | integer | 是 | minimum=1.0 | Applicationid |
| `action` | enum ["accept", "reject"] | 是 | — | Action |
| `clientCommandId` | string | 是 | minLength=1; maxLength=128 | Clientcommandid |

## ApplicationHandleResult

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `success` | boolean | 否 | default=true; const=true | Success |
| `application` | MessageApplication | 是 | — | application |
| `canChat` | boolean | 是 | — | Canchat |

## ChatPermissionResponse

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `userId` | integer | 是 | — | Userid |
| `conversationId` | string | 否 | default="" | Conversationid |
| `sessionId` | integer / null | 否 | — | Sessionid |
| `canChat` | boolean | 是 | — | Canchat |
| `reason` | string | 是 | — | Reason |

## HTTPValidationError

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `detail` | array[ValidationError] | 否 | — | Detail |

## MarkAllReadResult

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `success` | boolean | 否 | default=true; const=true | Success |
| `updatedCount` | integer | 是 | minimum=0.0 | Updatedcount |
| `unreadTotal` | integer | 否 | default=0; const=0 | Unreadtotal |

## MessageApplication

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `id` | integer | 是 | — | Id |
| `userId` | integer | 是 | — | Userid |
| `avatar` | string / null | 是 | — | Avatar |
| `name` | string | 是 | — | Name |
| `message` | string | 是 | — | Message |
| `time` | integer | 是 | — | Time |
| `status` | enum ["pending", "accepted", "rejected", "expired"] | 是 | — | Status |
| `statusText` | string | 是 | — | Statustext |
| `direction` | enum ["in", "out"] | 是 | — | Direction |

## MessageApplicationPage

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `list` | array[MessageApplication] | 是 | — | List |
| `nextCursor` | string | 是 | — | Nextcursor |
| `hasMore` | boolean | 是 | — | Hasmore |
| `total` | integer | 是 | minimum=0.0 | Total |
| `pendingCount` | integer | 否 | default=0; minimum=0.0 | Pendingcount |

## MessageChatItem

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `id` | integer | 是 | — | Id |
| `clientMessageId` | string / null | 否 | — | Clientmessageid |
| `type` | enum ["text", "image", "voice", "video"] | 是 | — | Type |
| `content` | string | 是 | — | Content |
| `time` | integer | 是 | — | Time |
| `isMine` | boolean | 是 | — | Ismine |
| `senderAvatar` | string / null | 否 | — | Senderavatar |
| `revoked` | boolean | 否 | default=false | Revoked |

## MessageConversation

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `id` | integer | 是 | — | Id |
| `conversationId` | string | 是 | — | Conversationid |
| `userId` | integer | 是 | — | Userid |
| `avatar` | string / null | 是 | — | Avatar |
| `name` | string | 是 | — | Name |
| `lastMessage` | string | 是 | — | Lastmessage |
| `time` | integer | 是 | — | Time |
| `unreadCount` | integer | 是 | minimum=0.0 | Unreadcount |
| `online` | boolean | 否 | default=false | Online |
| `messageType` | enum ["text", "image", "voice", "video"] | 否 | default="text" | Messagetype |
| `type` | string | 否 | default="chat"; const="chat" | Type |
| `matched` | boolean | 否 | default=true | Matched |
| `canChat` | boolean | 否 | default=true | Canchat |

## MessageConversationPage

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `list` | array[MessageConversation] | 是 | — | List |
| `nextCursor` | string | 是 | — | Nextcursor |
| `hasMore` | boolean | 是 | — | Hasmore |
| `total` | integer | 是 | minimum=0.0 | Total |
| `unreadTotal` | integer | 是 | minimum=0.0 | Unreadtotal |

## MessageRevokeResult

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `success` | boolean | 否 | default=true; const=true | Success |
| `messageId` | integer | 是 | — | Messageid |

## MessageSendRequest

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `userId` | integer | 是 | minimum=1.0 | Userid |
| `content` | string | 否 | default=""; maxLength=5000 | Content |
| `type` | enum ["text", "image", "voice", "video"] | 否 | default="text" | Type |
| `clientMessageId` | string | 是 | minLength=1; maxLength=128 | Clientmessageid |
| `mediaId` | integer / null | 否 | — | Mediaid |

## MessageSendResult

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `success` | boolean | 否 | default=true; const=true | Success |
| `messageId` | integer | 是 | — | Messageid |
| `message` | MessageChatItem | 是 | — | message |
| `deduplicated` | boolean | 否 | default=false | Deduplicated |

## ParentAlerts

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `enabled` | boolean | 是 | — | 页内提醒当前是否开启 |
| `latestEventId` | integer | 否 | default=0 | 当前子女申请与消息提醒事件最大ID，仅作变化标记；无事件为0 |
| `unreadCount` | integer | 否 | default=0 | 当前可见会话未读总数 |
| `pendingCount` | integer | 否 | default=0 | 子女收到的待回应申请数量 |

## ParentApplyRequest

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `note` | string | 是 | minLength=1; maxLength=120 | 认识申请附言，去首尾空白后不可为空；相同待回应申请的重试必须相同 |

## ParentApplyResult

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `success` | boolean | 否 | default=true; const=true | 业务操作成功，固定true；失败使用HTTP错误状态 |
| `applicationId` | integer | 是 | — | 现有match_apply申请记录ID |
| `applyStatus` | string | 否 | default="pending"; const="pending" | 发出认识申请后固定pending，聊天仍需对方接受 |
| `remainingApplications` | integer | 是 | — | 现有子女主体今日剩余次数；包含子女本人发起的申请，不得在客户端猜测扣减 |
| `deduplicated` | boolean | 否 | default=false | 是否复用已有同内容待回应申请 |

## ParentCandidate

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `id` | integer | 是 | — | 资源标识；context 为 parent:父母用户ID，其余资源为数据库整数ID |
| `displayName` | string | 是 | — | 子女或候选的显示称呼 |
| `genderText` | string | 是 | — | 男、女或未公开 |
| `birthYear` | integer | 是 | — | 已实名认证的出生年份；父母编辑必须与已核验年份完全一致；资料无权访问时为0 |
| `city` | string | 是 | — | 城市显示名称；编辑时支持唯一城市名称、去市后缀名称或行政编码 |
| `height` | string | 是 | — | 带cm单位的身高显示值；受隐私限制时为未公开 |
| `education` | string | 是 | — | 学历显示名称；遵循数据库学历编码及本人隐私设置 |
| `job` | string | 是 | — | 职业；未公开时返回未公开，编辑时可为空 |
| `income` | string | 否 | default="未公开" | 父母视图当前固定未公开 |
| `certificationText` | string | 是 | — | 根据真实认证信息生成的展示标签 |
| `avatar` | string | 否 | default="" | 父母视图固定空字符串，不下发原始头像 |
| `clearAvatar` | string | 否 | default="" | 仅候选本人许可且详情可见时下发清晰头像URL，其他情形为空 |
| `introduction` | string | 否 | default="" | 已获准展示的自我介绍 |
| `datingNotes` | string | 否 | default="是否继续由双方本人决定。" | 认识与沟通边界说明 |
| `expectations` | array[string] | 否 | — | 公开期待列表，未提供时[] |
| `liked` | boolean | 否 | default=false | 该候选在子女主体下的私密喜欢状态；不通知对方 |
| `canViewClearPhoto` | boolean | 否 | default=false | 当前详情是否获准下发清晰照片；列表始终false |

## ParentCandidatePage

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `items` | array[ParentCandidate] | 是 | — | 本页资源数组；无结果为[]，元素结构按引用模型展开 |
| `page` | integer | 是 | — | 当前页，从1开始 |
| `pageSize` | integer | 是 | — | 每页条数，默认20，父母候选最多20 |
| `total` | integer | 是 | — | 满足可见性条件的总条数 |
| `hasMore` | boolean | 是 | — | 是否还有下一页 |

## ParentChild

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `id` | integer | 是 | — | 资源标识；context 为 parent:父母用户ID，其余资源为数据库整数ID |
| `displayName` | string | 是 | — | 子女或候选的显示称呼 |
| `birthYear` | integer | 是 | — | 已实名认证的出生年份；父母编辑必须与已核验年份完全一致；资料无权访问时为0 |
| `city` | string | 是 | — | 城市显示名称；编辑时支持唯一城市名称、去市后缀名称或行政编码 |
| `job` | string | 是 | — | 职业；未公开时返回未公开，编辑时可为空 |
| `introduction` | string | 是 | — | 已获准展示的自我介绍 |
| `authorizationStatus` | enum ["pending", "granted", "revoked", "expired"] | 是 | — | pending 待授权、granted 当前有效、revoked 已撤销或资格失效、expired 超期 |
| `authorizationExpiresAt` | string | 是 | — | 授权到期 UTC ISO 8601 时间；未授予时为空字符串 |
| `profileProgress` | number | 是 | — | 现有资料完整度分数，范围0至100 |

## ParentChildUpdate

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `displayName` | string | 是 | minLength=1; maxLength=64 | 子女或候选的显示称呼 |
| `birthYear` | integer | 是 | minimum=1940.0 | 已实名认证的出生年份；父母编辑必须与已核验年份完全一致；资料无权访问时为0 |
| `city` | string | 是 | minLength=1; maxLength=64 | 城市显示名称；编辑时支持唯一城市名称、去市后缀名称或行政编码 |
| `job` | string | 否 | default=""; maxLength=128 | 职业；未公开时返回未公开，编辑时可为空 |
| `introduction` | string | 否 | default=""; maxLength=1000 | 已获准展示的自我介绍 |

## ParentConsentAccept

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `code` | string | 是 | minLength=32; maxLength=128; pattern="^[A-Za-z0-9_-]+$" | 邀请操作为保密随机邀请码；releaseGate 为服务能力代码；仅服务器存储邀请哈希 |
| `confirmed` | boolean | 是 | const=true | 子女明确确认；只接受JSON布尔true，拒绝false、1和字符串 |
| `consentVersion` | string | 否 | default="parent-consent@1"; const="parent-consent@1" | 明确授权政策版本parent-consent@1；未知版本拒绝授予或代理操作 |
| `days` | integer | 否 | default=30; minimum=1.0; maximum=90.0 | 子女确认的授权有效天数，整数1至90，默认30 |

## ParentConsentCode

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `code` | string | 是 | minLength=32; maxLength=128; pattern="^[A-Za-z0-9_-]+$" | 邀请操作为保密随机邀请码；releaseGate 为服务能力代码；仅服务器存储邀请哈希 |

## ParentConsentPreview

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `parentId` | integer | 是 | — | 关系所属父母的用户ID；不得冒用其他账号 |
| `parentName` | string | 是 | — | 被授权父母的显示名称 |
| `consentVersion` | string | 是 | — | 明确授权政策版本parent-consent@1；未知版本拒绝授予或代理操作 |
| `scopes` | array[string] | 是 | — | 子女确认前必须逐项展示的五项授权范围 |
| `expiresAt` | string | 是 | — | 邀请或授权到期UTC ISO 8601时间；未生成时可为空字符串 |

## ParentContext

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `id` | string | 是 | — | 资源标识；context 为 parent:父母用户ID，其余资源为数据库整数ID |
| `mode` | string | 否 | default="parent"; const="parent" | 父母上下文固定为parent |
| `dataMode` | string | 否 | default="http"; const="http" | 本服务固定http；Mock仅供显式测试模式 |
| `parent` | ParentIdentity | 是 | — | 当前Token对应父母身份 |
| `child` | ParentChild / null | 否 | — | 当前绑定子女及授权状态；未绑定时为null，失效时不下发子女私密资料 |
| `quota` | ParentQuota | 是 | — | 子女主体的每日申请额度 |
| `releaseGate` | ParentReleaseGate | 否 | — | 后端能力声明 |
| `messageNotifications` | boolean | 否 | default=true | 父母页内申请与消息提醒开关；不代表操作系统或微信订阅推送 |

## ParentIdentity

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `id` | integer | 是 | — | 资源标识；context 为 parent:父母用户ID，其余资源为数据库整数ID |
| `name` | string | 是 | — | 当前账号显示名称 |
| `avatar` | string | 否 | default="" | 父母视图固定空字符串，不下发原始头像 |
| `realNameStatus` | enum ["missing", "reviewing", "passed", "rejected"] | 是 | — | 实名状态：missing 未提交、reviewing 审核中、passed 通过、rejected 未通过 |

## ParentInvitation

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `code` | string | 是 | — | 邀请操作为保密随机邀请码；releaseGate 为服务能力代码；仅服务器存储邀请哈希 |
| `expiresAt` | string | 是 | — | 邀请或授权到期UTC ISO 8601时间；未生成时可为空字符串 |
| `consentVersion` | string | 是 | — | 明确授权政策版本parent-consent@1；未知版本拒绝授予或代理操作 |

## ParentLikeRequest

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `liked` | boolean | 是 | — | 该候选在子女主体下的私密喜欢状态；不通知对方 |

## ParentLikeResult

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `success` | boolean | 否 | default=true; const=true | 业务操作成功，固定true；失败使用HTTP错误状态 |
| `userId` | integer | 是 | — | 目标候选用户ID |
| `liked` | boolean | 是 | — | 该候选在子女主体下的私密喜欢状态；不通知对方 |

## ParentPreference

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `messageNotifications` | boolean | 否 | default=true | 父母页内申请与消息提醒开关；不代表操作系统或微信订阅推送 |
| `allowParentPhoto` | boolean | 否 | default=false | 当前账号本人许可父母视图看清晰照片；默认关闭，仅详情可使用，列表和聊天始终脱敏 |

## ParentPreferenceUpdate

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `messageNotifications` | boolean / null | 否 | — | 父母页内申请与消息提醒开关；不代表操作系统或微信订阅推送 |
| `allowParentPhoto` | boolean / null | 否 | — | 当前账号本人许可父母视图看清晰照片；默认关闭，仅详情可使用，列表和聊天始终脱敏 |

## ParentQuota

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `dailyTotal` | integer | 否 | default=3 | 父母协助每日申请总额，固定3次，按UTC日期重置 |
| `remainingApplications` | integer | 是 | minimum=0.0 | 现有子女主体今日剩余次数；包含子女本人发起的申请，不得在客户端猜测扣减 |

## ParentRelationship

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `parentId` | integer | 是 | — | 关系所属父母的用户ID；不得冒用其他账号 |
| `parentName` | string | 是 | — | 被授权父母的显示名称 |
| `childId` | integer / null | 是 | — | 绑定子女用户ID；尚未绑定时null |
| `status` | enum ["pending", "granted", "revoked", "expired"] | 是 | — | 授权状态：pending待授权、granted有效、revoked已撤销、expired已过期 |
| `expiresAt` | string | 是 | — | 邀请或授权到期UTC ISO 8601时间；未生成时可为空字符串 |
| `consentVersion` | string | 是 | — | 明确授权政策版本parent-consent@1；未知版本拒绝授予或代理操作 |

## ParentRelationshipPage

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `items` | array[ParentRelationship] | 是 | — | 本页资源数组；无结果为[]，元素结构按引用模型展开 |

## ParentReleaseGate

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `productionReady` | boolean | 否 | default=true | 服务具备关系校验及脱敏能力；不表示当前环境已部署或已通过发布验收 |
| `code` | string | 否 | default="OK" | 邀请操作为保密随机邀请码；releaseGate 为服务能力代码；仅服务器存储邀请哈希 |
| `message` | string | 否 | default="服务端逐次校验授权并过滤隐私字段" | 服务状态说明或申请附言，取决于对应模型 |

## ParentReportRequest

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `reasonId` | string | 是 | minLength=1; maxLength=64 | 举报原因，复用现有安全举报类型；other表示其他 |
| `detail` | string | 否 | default=""; maxLength=1000 | 举报补充描述，可为空 |

## ParentSuccess

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `success` | boolean | 否 | default=true; const=true | 业务操作成功，固定true；失败使用HTTP错误状态 |

## ReportResponse

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `id` | integer | 是 | — | Id |
| `target_user_id` | integer | 是 | — | Target User Id |
| `target_type` | enum ["user", "post", "comment", "paper_plane"] | 否 | default="user" | Target Type |
| `target_id` | integer / null | 否 | — | Target Id |
| `type` | string | 是 | — | Type |
| `status` | enum [0, 1, 2] | 是 | — | Status |
| `created_at` | string | 是 | format="date-time" | Created At |

## ValidationError

| 字段 | JSON 类型 | 输入必填 | 默认与约束 | 业务含义 |
| --- | --- | --- | --- | --- |
| `loc` | array[string / integer] | 是 | — | Location |
| `msg` | string | 是 | — | Message |
| `type` | string | 是 | — | Error Type |
| `input` | object | 否 | — | Input |
| `ctx` | object | 否 | — | Context |
