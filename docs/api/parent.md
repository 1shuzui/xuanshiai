# 父母端授权与代理业务接口

更新日期：2026-09-06。接口位于本仓库 `app/api/routes/parent.py`，完整前缀 `/api/v1/parent`。

这是父母账号在成年子女明确授权后，操作现有子女资料、私密喜欢、认识申请与文字聊天的服务。它复用原有用户、申请、匹配、会话、屏蔽、举报和通知记录，父母身份由当前访问令牌确定。客户端传入的 `child_id` 仅是待校验资源标识。

## 契约入口

- [全部接口、请求示例、成功响应和逐字段模型](parent-contract.generated.md)：覆盖每个 path/query/body 参数及嵌套返回结构，由实际 OpenAPI 生成。
- [独立 OpenAPI 文件](parent.openapi.json)：可导入接口调试工具；更新命令 `python scripts/export_parent_api_docs.py`。
- [消息中心](message.md)：父母消息复用其中的分页、申请和文字消息模型。
- [数据库迁移与运行说明](../parent-emotion-repair.md)。

所有接口要求 `Authorization: Bearer <access_token>`、有效登录会话、正常账号和已绑定手机号。写 JSON 时用 `Content-Type: application/json`。成功响应直接返回 JSON 业务对象，没有 `data` 外层；前端 `request()` 统一添加 `success/data/code/message` 包装。

## 新增接口与权限

| 方法与相对路径 | 用途 | 额外权限 |
| --- | --- | --- |
| GET `/context` | 当前父母身份、绑定子女、额度及服务能力 | 失效授权只返回状态，不返回子女资料 |
| POST `/invitations` | 生成24小时邀请；返回201 | 父母实名通过；无正在生效的授权；60秒生成间隔 |
| POST `/invitations/preview` | 子女查看邀请方、五项范围和截止时间 | 有效邀请码；不可给自己授权 |
| POST `/invitations/accept` | 子女明确确认授权 | 子女实名通过且按生日计算已成年；版本相符 |
| GET `/relationships` | 查看本人作为父母或子女的授权记录 | 只返回本人相关记录 |
| DELETE `/relationships/{parent_id}` | 撤销或拒绝继续授权 | 关系中的父母或子女；可安全重试 |
| GET/PATCH `/preferences` | 读取或更新本人提醒/照片许可 | 仅当前账号；未提交字段保持原值 |
| PUT `/children/{child_id}` | 代完善昵称、城市、职业、介绍 | 有效授权；出生年份只能回传已核验值 |
| GET `/children/{child_id}/candidates` | 推荐或私密喜欢分页 | 有效授权；推荐还使用现有资料完整度门槛 |
| GET `/children/{child_id}/candidates/{target_id}` | 受隐私保护的详情 | 有效授权、候选可见且未双向屏蔽；复用浏览额度 |
| PUT `/children/{child_id}/likes/{target_id}` | 设置私密喜欢状态 | 有效授权；`liked` 是目标状态 |
| POST `/children/{child_id}/applications/{target_id}` | 发出认识申请 | 有效授权、实名/资料/额度/双向屏蔽规则均通过 |
| PUT `/children/{child_id}/blocks/{target_id}` | 以子女主体屏蔽候选 | 有效授权；喜欢、推荐、申请和聊天随后过滤该对象 |
| POST `/children/{child_id}/reports/{target_id}` | 以父母自身身份举报 | 仍须拥有该子女关系；撤销后也可举报 |
| GET `/children/{child_id}/message/list` | 子女会话分页 | 有效授权；双方已同意的会话 |
| GET `/children/{child_id}/message/applications` | 收到/发出申请分页 | 有效授权；`direction=incoming/outgoing` |
| GET `/children/{child_id}/message/chat/permission` | 聊天权限 | 有效授权、双方同意、未屏蔽 |
| GET `/children/{child_id}/message/chat` | 子女聊天记录 | 同上；媒体与头像脱敏 |
| POST `/children/{child_id}/message/send` | 发送文字消息 | 同上；仅 `type=text` 且不允许 `mediaId` |
| POST `/children/{child_id}/message/application/handle` | 同意/拒绝收到的申请 | 有效授权；申请确为子女收到；核验申请对方 |
| POST `/children/{child_id}/message/read-all` | 标记会话已读 | 有效授权 |
| DELETE `/children/{child_id}/message/messages/{message_id}` | 撤回子女发出的消息 | 有效授权并遵守原有消息撤回权限与时间窗口 |
| GET `/children/{child_id}/alerts` | 页内提醒摘要 | 有效授权；不发送系统推送 |

## 子女确认与状态流转

邀请只保存 SHA-256 哈希，原码仅生成时返回；不要放进 URL、日志或分析事件。子女输入邀请码后先预览父母姓名与范围，再勾选确认。POST accept 的 `confirmed` 只接受 JSON 布尔 `true`，非法示例包括 `false`、`1`、`"true"`；`consentVersion` 必须为 `parent-consent@1`；`days` 为1至90的整数，默认30，`365` 或 `30.5` 非法。

五项授权为：代完善资料、查看推荐与私密喜欢、发送和处理认识申请、双方同意后的文字聊天、页内申请与消息提醒。以预览响应实际的五项文案为准。此授权不允许交换联系方式、媒体上传、代付费、访问社区或情感实验室。

数据库 `pending → granted → revoked`。到期不依赖定时任务；每次请求按 UTC 计算并对外返回 `expired`。双方任一账号冻结、实名失效、政策版本不一致都会阻止代理业务。重复确认原邀请不延长有效期；续期必须重新生成邀请并由子女再次确认。首期一个父母账号始终绑定一个子女；已绑定后不接受另一子女凭新码偷偷替换关系。

子女或父母均可撤销。撤销清除邀请码，保留关系和审计记录；失效关系不能读取子女昵称、职业、介绍、推荐、会话和提醒。不存在关系返回 `child:null`。此时额度为0，前端显示授权入口。

## 分页、幂等与额度

候选 GET 的 `liked=false` 为推荐，`true` 为喜欢；`page` 默认1、范围1至1000，`pageSize` 默认20、范围1至20。返回 `items/page/pageSize/total/hasMore`。非法示例：`page=0`、`pageSize=100`。消息分页使用原有 `list/nextCursor/hasMore/total`，不能误读为 `items`；`cursor` 是非负十进制偏移，`pageSize` 范围1至50。

申请以现有 `match_apply` 为权威。相同子女、候选、同内容的待回应申请返回原ID，`deduplicated=true`，不扣第二次额度；不同附言重试返回409。关系锁与按固定顺序取得的用户锁使并发相同申请只创建一次。父母协助最多每日3次，并复用子女已有申请额度；本人申请计入已用额度。按UTC日期重置，待回应/接受/过期占用额度，已拒绝申请退还额度。是否可继续以服务端返回的 `remainingApplications` 为准。

消息 `clientMessageId` 和处理申请的 `clientCommandId` 长度1至128。父母撤回消息的 query `clientCommandId` 长度1至100。服务端以父母ID和客户端键的SHA-256组成内部幂等键，区分父母与子女操作并保持数据库长度限制。发送响应回显原客户端ID用于前端确认；历史记录的客户端ID可能为内部命名空间键，记录身份以服务器消息ID为准。重复发送返回同一消息ID且 `deduplicated=true`；相同键不同内容返回409。

消息服务在幂等预留可能提交事务之后，再次锁定并校验授权和聊天权限，随后才允许写入。若子女在此间隙撤销授权，发送返回403且不新增消息。审计中的 `*_attempt` 表示经过校验的尝试，不能当成消息送达证明；送达与成功状态以原业务记录为准。

## 隐私与提醒

列表和聊天不下发清晰头像、手机号、微信号、媒体URL或嵌套附件。媒体消息保留消息类型与ID，内容为空，避免客户端拼回原图。候选详情只有在本人 `allowParentPhoto=true`、资料可见且不受详情限制时提供 `clearAvatar`。父母不能替候选开启许可。关闭许可后后续读取立即不再下发清晰照片。

`messageNotifications` 保存到父母本人的偏好。父母页面显示时每30秒读取 alerts；开启后根据事件ID变化提示并刷新消息区，隐藏页面停止轮询。首次进入只建立基线，不把历史事件当新提醒。该功能明确命名“页内申请与消息提醒”，不代表已接微信订阅消息。

## 错误契约与前端处理

| HTTP | 触发条件 | 前端处理 |
| --- | --- | --- |
| 401 | 登录缺失、失效或会话撤销 | 重新登录；旧账号迟到的401不得清除新账号登录 |
| 403 | 未实名、未成年、错误子女、授权失效、无聊天权限、屏蔽、非文字消息 | 清除代理缓存并刷新context，展示对应门禁；不要回退Mock |
| 404 | 邀请/关系/候选/申请/消息不存在或不可见 | 展示不可用并返回列表，不泄露资源归属 |
| 409 | 有效授权下重建邀请、已绑定其他子女、申请内容冲突、幂等请求处理中 | 展示服务端原因；同一在途操作可稍后原样重试 |
| 422 | Schema不符、未知城市、非核验出生年份、非法邀请码或确认参数 | 修正输入后重试 |
| 429 | 邀请生成太频繁或认识额度耗尽 | 显示限制；不要本地扣减或制造额外次数 |
| 500/503/网络异常 | 存储或基础服务异常 | 保留可重试状态；不得显示业务成功 |

业务拒绝示例：`{"detail":"父母实名或子女授权已失效，请重新取得授权"}`。字段校验示例：`{"detail":[{"type":"literal_error","loc":["body","consentVersion"],"msg":"Input should be 'parent-consent@1'","input":"unknown"}]}`。

`ACCOUNT_CHANGED` 是前端请求层的本地失败代码，不是后端HTTP状态；用于丢弃切换账号后的迟到响应。有效邀请码之外的保密信息不能在错误文案中回显。

## 兼容性与变更记录

2026-09-06 新增本组接口，不改普通用户 `/message/*` 的主体。父母前端从独立Mock切到统一 `USE_MOCK` 对应数据源，普通用户消息同步切换，确保申请双方操作同一套记录。旧 Mock 数据不导入真实用户库，也不自动生成授权。部署时先执行新增表迁移，再部署后端和前端；旧后端不存在父母路由时，客户端显示失败，不假装业务已完成。
