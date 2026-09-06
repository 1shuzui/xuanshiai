# 情感实验室 MBTI 接口

接口前缀：`/api/v1`。所有接口需要 `Authorization: Bearer <access_token>`，并要求当前账号通过已验证用户校验。响应不含通用 `data` 包装；失败为 `{"detail":"错误原因"}`。当前仅提供已授权的 MBTI `mbti-core@2`，固定 60 题、1–7 级量表，不提供荣格八维、九型人格或其他 demo 能力。

## 1. 关键约定

- 每次创建会话都会保存题文、选项、维度、计分方向和结果文案版本快照；后续题库升级不影响旧会话。
- 客户端只会收到题目 `id`、`text`、`options`，不会收到计分方向或极性。
- 提交必须覆盖该会话全部题目，题目 ID 不可重复、不可越出会话快照，答案必须是当前题目的合法选项值。
- MBTI 结果用于自我了解，不构成心理诊断或专业建议。

## 2. 摘要与创建

### `GET /emotion-lab/summary`

无请求参数。返回字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `assessments` | array | 当前开放定义；每项含 `id`、`version`、`kind`、`title`、`authorization`、`canStart`、`questionCount`、`scale`、`dimensions`、`tieBreak`、`resultCopyVersion` |
| `authorization` | object | 当前为 `{"status":"approved","label":"内容已授权","reviewedAt":null}` |
| `manualTypes` | array[string] | 16 种合法 MBTI 类型 |
| `activeSession` | object/null | 最新进行中会话优先，否则最新已完成会话；没有时为 `null` |
| `profileSource` | object/null | 已确认同步到资料的来源；没有时为 `null` |
| `disclaimer` / `disclaimerVersion` | string | 当前版本的非诊断声明与文案版本 |

### `POST /emotion-lab/sessions`

```json
{"assessmentId":"mbti-core"}
```

`assessmentId` 可省略，默认 `mbti-core`，长度 1–64。成功返回会话快照，状态为 `in_progress`。同一用户已有进行中会话返回 `409`，未知定义返回 `404`。

会话响应字段：`schemaVersion`（固定 2）、`id`、`definitionId`、`definitionVersion`、`resultCopyVersion`、`kind`、`status`、`questionIds`、`questions`、`answers`、`result`、`createdAt`、`updatedAt`。`questions[]` 仅含 `id`、`text`、`options[]`；选项为 `value`（1–7）和 `label`。新建响应中 `answers=[]`、`result=null`。

## 3. 保存、提交与放弃

### `PUT /emotion-lab/sessions/{session_id}/answers`

路径 `session_id` 长度 1–128。请求体：

```json
{"answers":[{"questionId":"mbti-16p-001","value":6}]}
```

`answers` 数组长度 1–100；每项 `questionId` 长度 1–128，`value` 为 1–7 的整数。服务端把本次答案与已有草稿合并，并按题目快照原始顺序返回。进行中会话可分批保存；已完成或已放弃会话返回 `409`。答案重复、题目不属于快照或答案不在题目允许选项中返回 `422`。

### `POST /emotion-lab/sessions/{session_id}/submit`

路径约束同保存接口，请求体也使用 `{"answers":[...]}`，但必须完整提交 60 道当前快照题。成功后返回 `status=completed` 与 `result`：

```json
{
  "id":"mbti-result:mbti-session-...",
  "sessionId":"mbti-session-...",
  "assessmentId":"mbti-core",
  "assessmentVersion":"mbti-core@2",
  "source":"assessment",
  "mbtiType":"ENFP",
  "dimensions":{"EI":{"E":67,"I":33},"SN":{"S":42,"N":58},"TF":{"T":33,"F":67},"JP":{"J":42,"P":58}},
  "resultCopy":{"version":"mbti-result-copy@2","title":"ENFP · MBTI 偏好结果","summary":"...","disclaimer":"结果仅用于自我了解，不构成心理诊断或专业建议。"},
  "completedAt":1785220000000
}
```

完成会话以相同完整答案重复提交时返回原始结果；提交不同答案、提交不完整或放弃会话分别返回 `409`、`422`、`409`。计分始终读取会话快照，不按当前题库随机重组或重新取题。

### `POST /emotion-lab/sessions/{session_id}/discard`

无请求体。只能放弃本人进行中会话，成功返回 `status=discarded`、`answers=[]`、`result=null`。重复放弃是安全的；已完成会话不可放弃，返回 `409`。

## 4. 明确确认后同步资料

### `PUT /emotion-lab/profile-source`

```json
{
  "mbtiType":"ENFP",
  "source":"assessment",
  "confirmed":true,
  "resultId":"mbti-result:mbti-session-..."
}
```

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `mbtiType` | string | 必填，16 种 MBTI 类型之一 |
| `source` | string | 必填，`assessment` 或 `self_reported` |
| `confirmed` | boolean | 必须为 `true`，避免页面自动覆盖资料 |
| `resultId` | string/null | `assessment` 必填；必须属于当前用户已完成会话且类型一致。手动设置必须省略或传 `null` |

成功返回 `mbtiType`、`source`、`assessmentVersion`（手动设置为 `null`）、`resultId`（手动设置为 `null`）、`confirmedAt`。服务端在同一事务中更新资料页 `user_profile.mbti` 和来源记录，并重新计算资料完整度。未确认、结果所有权不符或结果类型不符返回 `422`；登录失效返回 `401`。

## 5. 错误、版本与兼容性

常见状态码：`401` 登录失效，`404` 未知定义或不属于当前用户的会话，`409` 草稿冲突/已完成/已放弃，`422` 字段、答案或确认状态非法，`500` 历史快照损坏。前端遇到 `409` 应重新读取摘要，不得覆盖服务端会话。

本接口于 2026-07-28 新增，不修改旧资料读取接口。未来题库或文案变化必须使用新的 `definitionVersion` 和 `resultCopyVersion`；历史会话和结果按原版本继续可读。客户端不得依赖题目数组之外的计分字段，也不得把结果文案解释为诊断。

## 2026-09-06 持久化与来源修复

**变更内容**：公开请求、响应字段不改名。持久化结果及消息模型兼容camelCase与旧snake_case，修复提交后再次加载/确认失败。新会话的question_snapshot为包含questions、dimensionPoles、resultCopy的对象；其中题目是数组，结果文案与声明完整冻结。旧列表快照仅映射到不可变的mbti-core@2归档，不读取未来文案。

MySQL JSON可能重排对象键，计分固定按EI、SN、TF、JP组装类型，不能依赖dict顺序。百分比用整数半分四舍五入，12.5%为13%，与前端保持一致。同分取first_pole，四维都是50%时为ESTJ。新建草稿先锁用户行，并发创建一个成功、一个409；完成会话原答案重试返回原始结果。

**资料来源约束**：修改MBTI必须调用PUT /emotion-lab/profile-source并明确confirmed。通用PATCH /users/me/profile改变MBTI返回422；旧客户端回传与数据库相同的现值允许通过但不重新写入来源。只有完成本人结果才能使用assessment来源；self_reported仍要求用户确认。

**迁移**：旧结果JSON不用重算，旧已确认资料不被覆盖。新快照仍存现有JSON列，不另改表。旧版服务不识别新对象快照，因此回退必须保留兼容读取器。详见[修复与迁移说明](../parent-emotion-repair.md)。
