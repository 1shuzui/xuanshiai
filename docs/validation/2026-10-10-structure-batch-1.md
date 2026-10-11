# 第一批结构精简验证（2026-10-10）

计划：[后端计划](../plans/2026-10-10-structure-simplification.md)；完整分期计划位于关联前端 PR 的同名文件。

## 环境与边界

- 上游 main：`ce72b9e10e683cf9681606325ee9e8a0ba961350`；隔离 checkout，原 D: 工作区与未提交目录未修改。
- Windows、Python 3.12.4；`uv sync --locked --extra dev --python D:\anaconda3\python.exe` 成功，锁文件未改。
- 测试环境统一：`ENVIRONMENT=testing`、`AI_PROVIDER=mock`、`AI_MASTER_ENABLED=false`、`AUTO_INIT_DB=false`；`DATABASE_URL=mysql+aiomysql://ci:ci@127.0.0.1:1/ci_unreachable`、`REDIS_URL=redis://127.0.0.1:1/5`。没有复制开发/生产 `.env`，未调用付费 Provider 或真实数据服务。
- 沙箱内早期 pytest 导入停滞，无结果；只停止已核实路径的本任务进程，随后在同一隔离配置下运行成功。原项目 Python 3.14 环境缺少 openpyxl，未用于验收。

## 实际命令与结果

| 改动 | 实际验证 | 结果 |
| --- | --- | --- |
| Worker 唯一注册入口 | `.venv\Scripts\python.exe -u -m pytest tests/test_worker_registration.py -q` | 3 passed；两个全新进程导入顺序、全部 14 个 handler、search_suggest publisher、重复注册和独立 `--once --dry-run` |
| 无用投影 wrapper 删除 | 下方定向回归中的 `test_ai_memory_projection_shadow.py`、`test_ai_search_memory_projection.py`、`test_ai_feature_projection.py` | 通过；调用真实 search reader，覆盖缺投影、撤权、重新授权隔离、memory-only、shadow 日志脱敏与 canonical diff |
| 字段元数据贯通 | `.venv\Scripts\python.exe -u -m pytest tests/test_ai_profile_field_metadata.py tests/test_ai_profile_publish.py tests/test_ai_profile_entries.py -q` | 56 passed；含两个主体、首次确认/幂等回放、历史 NULL/旧 JSON、entry 元数据和 revision INSERT |
| 三项联合回归 | 下方完整命令 | 260 passed，9 warnings，退出码 0；还出现既有 audit flusher 退出时 pending-task 日志，未将它写成无告警通过 |
| 静态检查 | `.venv\Scripts\ruff.exe check app/services/ai/search.py app/services/ai/compatibility.py app/services/ai/recommend.py app/services/ai/features.py app/services/ai/profile.py app/services/ai/continuous.py tests/test_worker_registration.py tests/test_ai_profile_field_metadata.py tests/test_ai_memory_projection_shadow.py tests/integration/ai/test_ai_memory_projection_real_db.py tests/integration/ai/test_continuous_portrait_real_db.py` | All checks passed |
| Python 语法 | `.venv\Scripts\python.exe -m compileall -q` 加上述改动 Python 文件 | 退出码 0 |
| 补丁检查 | `git diff --check` | 通过 |

联合回归的实际命令（已设定上述环境）：

```powershell
.\.venv\Scripts\python.exe -u -m pytest `
  tests/test_worker_registration.py tests/test_worker_finalize_gate.py tests/test_worker_lease_safety.py `
  tests/test_ai_memory_projection_shadow.py tests/test_ai_search_memory_projection.py tests/test_ai_feature_projection.py `
  tests/test_ai_profile_field_metadata.py tests/test_ai_profile_publish.py tests/test_ai_profile_entries.py `
  tests/test_ai_profile_sessions.py tests/test_master_session.py `
  tests/test_ai_continuous_dual_journey.py tests/test_ai_continuous_memory.py `
  tests/test_ai_continuous_revision_dependencies.py tests/test_ai_continuous_routes.py tests/test_ai_continuous_docs.py `
  tests/test_ai_profile_preview.py tests/test_ai_moxiang_candidate_pool.py `
  -q --junitxml=../backend-targeted-results.xml
```

## 未运行与后续

- 本机真实 MySQL/Redis 集成 **NOT_RUN**：Docker 的 Linux engine 命名管道不存在，没有确认可隔离的本机临时实例。没有改连开发库或生产库。现有 GitHub CI integration job 创建自己的临时 MySQL/Redis；PR head 的实际结果在 PR 中记录。
- 为现有 continuous 实库冻结预览/整份确认/重放用例补充了 draft→revision 元数据逐字段相等断言（双主体），投影实库模式测试迁到真实 search reader；本机仅静态检查，不能声称这些实库用例已在本机通过。
- 既有 pytest asyncio 标记、Starlette 提示与审计任务退出日志另行处理；本批不扩大测试框架或关闭检查。
- 后续模块拆分、兼容协议退场与产品决策仅写计划，不在本批实施。

## 提交

- `15d1570f183a46e2c3bab3c4de41354bc015ccbd`：计划。
- `8d14a6c6761e007f897e45508b3a27291c95ce44`：Worker 注册入口及 CI。
- `4ec2b7b2300dfb0372a7ef13c898d9ba4cebe27d`：无用投影 wrapper、实际消费者测试及 CI。
- `37a0d1d5e4342d5be2268465896ec35c14d20d26`：维度/entry 元数据读写与重放、实库断言及 CI。

草稿 PR、最终 head SHA 和对应 CI 是动态状态，见关联 PR 的验证部分；不合并或部署。
