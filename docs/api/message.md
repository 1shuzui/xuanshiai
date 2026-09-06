# 消息中心接口

接口前缀：`/api/v1`。本文件中的接口均要求 `Authorization: Bearer <access_token>`，并通过已验证用户校验。所有成功响应直接返回 JSON 对象或数组，不再包裹 `data`；错误响应为 `{"detail":"错误原因"}`。

本组接口只服务普通用户主体。父母代子女主体、`childId` 及其关系授权不接受客户端传入，仍属于单独的父母关系服务范围。

## 1. 会话与申请

### `GET /message/list`

查询参数：`cursor`（字符串，默认空，只能为非负十进制偏移）、`pageSize`（整数，默认 20，范围 1–50）。

```http
GET /api/v1/message/list?cursor=0&pageSize=20
Authorization: Bearer <access_token>
```

返回分页结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `list` | array | 可聊天、未互相拉黑的会话，按最近消息倒序 |
| `list[].id` / `conversationId` | integer / string | 会话数据库 ID 与稳定展示 ID |
| `list[].userId` | integer | 对方用户 ID |
| `avatar` / `name` | string/null / string | 对方摘要；头像未设置时为 `null` |
| `lastMessage` / `time` | string / integer | 最后消息与 Unix 毫秒时间戳 |
| `unreadCount` | integer | 当前用户在该会话的未读数，最小为 0 |
| `nextCursor` / `hasMore` / `total` | string / boolean / integer | 分页游标、是否还有更多和总数 |
| `unreadTotal` | integer | 当前全部可访问会话的未读总数 |

无会话时返回 `{"list":[],"nextCursor":"","hasMore":false,"total":0,"unreadTotal":0}`。无效游标或 `pageSize` 返回 `422`。

### `GET /message/applications`

查询参数与会话分页相同，另有 `direction`：`incoming`（默认，收到的）或 `outgoing`（发出的）。

```http
GET /api/v1/message/applications?direction=incoming&cursor=0&pageSize=20
Authorization: Bearer <access_token>
```

`list[]` 包含 `id`、`userId`、`avatar`、`name`、`message`、`time`、`status`、`statusText`、`direction`。`status` 仅为 `pending`、`accepted`、`rejected`、`expired`；`direction` 为 `in` 或 `out`。分页字段与会话分页一致；`pendingCount` 仅在 `direction=incoming` 时统计收到且待处理的申请，发出栏固定为 0。

### `POST /message/application/handle`

仅可处理本人收到且仍为 `pending` 的申请。

```http
POST /api/v1/message/application/handle
Authorization: Bearer <access_token>
Content-Type: application/json

{"applicationId":91,"action":"accept","clientCommandId":"application-accept-91-001"}
```

| 请求字段 | 类型 | 规则 |
| --- | --- | --- |
| `applicationId` | integer | 必填，`>=1`，必须是当前用户收到的申请 |
| `action` | string | 必填，`accept` 或 `reject` |
| `clientCommandId` | string | 必填，1–128 字符；同一用户和操作键只能重放相同请求 |

成功响应：`{"success":true,"application":{...},"canChat":true}`。`canChat` 只有接受成功时才可能为 `true`。重复相同命令返回首次最终结果；同一键配不同请求返回 `409`。申请不存在、非本人或状态已变更分别返回 `404`、`403`、`409`。

## 2. 聊天权限、记录与已读

### `GET /message/chat/permission`

```http
GET /api/v1/message/chat/permission?userId=23
Authorization: Bearer <access_token>
```

`userId` 为必填整数且 `>=1`。响应包含 `userId`、`conversationId`、`sessionId`、`canChat`、`reason`。前端在进入会话、发送任何消息、上传媒体和联系方式交换前都必须重新调用；`canChat=false` 时不得展示或访问聊天资源。

### `GET /message/chat`

查询参数：`userId`（必填整数，`>=1`）。成功返回最多 50 条 `MessageChatItem`：`id`、`clientMessageId`（可空）、`type`（`text|image|voice|video`）、`content`、`time`（毫秒）、`isMine`、`senderAvatar`（可空）、`revoked`。无权限返回 `403`，不会返回部分消息。

### `POST /message/send`

```json
{
  "userId": 23,
  "type": "text",
  "content": "你好，很高兴认识你。",
  "clientMessageId": "chat-23-001"
}
```

| 请求字段 | 类型 | 规则 |
| --- | --- | --- |
| `userId` | integer | 必填，`>=1`，需重新通过双方聊天权限检查 |
| `type` | string | `text`、`image`、`voice`、`video` |
| `content` | string | 文本必填，去除首尾空白，最长 5000；媒体消息必须为空 |
| `mediaId` | integer/null | 图片、语音、视频必填；必须是当前用户已上传且 `purpose=chat` 的就绪媒体 |
| `clientMessageId` | string | 必填，1–128 字符；用于客户端重试去重 |

成功响应为 `{"success":true,"messageId":501,"message":{...},"deduplicated":false}`。相同客户端 ID 且请求完全相同返回原响应并将 `deduplicated` 标识为重放结果；同 ID 的不同内容返回 `409`。无聊天权限为 `403`，未拥有或未就绪的媒体为 `403/422`，字段不合法为 `422`。

### `DELETE /message/messages/{message_id}`

路径参数 `message_id` 为本人发送的消息 ID，且必须 `>=1`。查询参数 `clientCommandId` 必填，长度 1–128。

```http
DELETE /api/v1/message/messages/501?clientCommandId=revoke-501-001
Authorization: Bearer <access_token>
```

成功返回 `{"success":true,"messageId":501}`。撤回后记录保留，但内容对双方显示“消息已撤回”，媒体 URL 不再返回。撤回操作使用命令幂等；非本人消息、已撤回或不存在的消息不会被静默视为成功，分别返回 `403/409/404`。

### `POST /message/read-all`

无请求体。成功返回 `{"success":true,"updatedCount":2,"unreadTotal":0}`。仅更新当前用户在有效、未拉黑会话中的未读消息；重复调用安全，且不会更改对方已读状态。

## 3. 聊天媒体

### `POST /message/media/uploads`

`multipart/form-data`，字段 `peerUserId`（整数，`>=1`）和 `file`（必填上传文件）。上传前服务端重新检查双方聊天权限。成功状态为 `201`，返回既有媒体对象，至少包含 `id`、`mediaType`、`fileUrl`/`url`。前端只能把返回 `id` 作为 `/message/send` 的 `mediaId`；不可直接发送本地临时路径。

无聊天权限返回 `403`；类型、大小、所有权或文件校验失败按媒体服务返回 `422/403`。上传成功后发送失败可使用相同 `mediaId` 重试；上传失败必须重新选择媒体。

## 4. 联系方式交换

所有联系方式接口均在读取或写入前重新检查双方聊天权限。数据库仅保存加密值；`pending` 与 `rejected` 响应的 `contactValue` 始终为 `null`。只有接收方明确 `accept` 后，双方列表才可读到明文。

### `GET /message/contact-exchanges`

查询参数 `userId` 必填且 `>=1`。返回 `{"list":[...]}`，列表最多 20 条，按创建时间倒序。单条字段为 `id`、`userId`（对方）、`contactType`（`phone|wechat`）、`status`（`pending|accepted|rejected`）、`requestedByMe`、`contactValue`（接受前为 `null`）、`createdAt`、`respondedAt`（未处理为 `null`）。

### `POST /message/contact-exchanges`

```json
{
  "userId": 23,
  "contactType": "wechat",
  "contactValue": "xuan-shi-ai",
  "clientCommandId": "contact-create-23-001"
}
```

`userId` 必填且 `>=1`；`contactType` 为 `phone` 或 `wechat`；`clientCommandId` 必填、1–128 字符。微信号去首尾空白后长度至少 6、最多 64；手机号类型不接受 `contactValue`，服务端只取当前账号已验证手机号，未绑定返回 `403`。成功返回新建的联系方式对象，初始 `status=pending`、`contactValue=null`。创建命令幂等，同键不同载荷返回 `409`。

### `POST /message/contact-exchanges/{exchange_id}/respond`

路径参数 `exchange_id` 为整数且 `>=1`。请求体：`{"action":"accept","clientCommandId":"contact-accept-31-001"}`；`action` 仅可为 `accept` 或 `reject`，命令 ID 长度为 1–128。仅接收者可处理本人收到的待处理请求。成功响应为更新后的对象：接受时返回解密后的 `contactValue`，拒绝时为 `null`。非接收者、重复处理、无权限分别返回 `403`、`409`、`403`。

## 5. 兼容性与错误处理

本 facade 新增于 2026-07-28，不删除原 `/chat/*` 和发现申请接口；旧客户端可继续使用旧接口。常见错误：`401` 登录失效（客户端清理本地凭据并返回登录）、`403` 权限/双方同意/媒体所有权失败（保持原界面状态）、`404` 资源不存在、`409` 幂等键冲突或状态已变化（刷新列表确认最终状态）、`422` 参数不合法、`500` 加密数据损坏或服务异常（不展示敏感字段）。

## 2026-09-06 父母代理消息接入

普通/message接口始终使用登录用户。父母请求使用独立的/parent/children/{child_id}/message路径；关系、期限与授权范围由服务端校验，不能把subjectMode或childId拼进普通路由来冒用子女。父母接口逐字段契约见[parent.md](parent.md)。

**变更内容**：消息和MBTI相关camelCase模型现同时接受camelCase输入与存储，以及旧snake_case字段；响应命名保持不变。消息重放明确返回deduplicated=true。代理写入在幂等预留之后再次验证授权；普通消息调用无需传入代理回调。父母/普通用户前端共同遵循全局USE_MOCK，保障申请双方操作同一后端。

屏蔽后的申请分页会过滤该对象，已被屏蔽的申请对方不能通过同意操作建立聊天。
