# 后端结构精简第一批（2026-10-10）

跨仓完整计划：[前端分批实施计划](https://github.com/kx-learn/xuanshiai-vue/blob/refactor/structure-batch-1/docs/plans/2026-10-10-structure-simplification.md)。

本仓基线 `ce72b9e10e683cf9681606325ee9e8a0ba961350`，远端 main 与既有分析一致；独立 checkout/分支 `refactor/structure-batch-1`，不修改原用户分支、未跟踪目录或本机 memories。

本批每项独立提交：

1. 移除 search/compatibility/recommend 的反向导入注册，仅由 ai_worker.register_business_handlers 注册；新进程验证所有 handler、search_suggest 完成后 publisher、幂等和独立 Worker dry-run。
2. 移除只有定义/测试引用的 features.read_projection_with_mode 及其私有辅助；有效测试改为覆盖真实 memory 读取和消费者，保留 canonical diff、日志不含原文及 memory 缺失不回退旧值的覆盖。
3. profile_dimension 从已有 SELECT/草稿对象完整传到 JSON/幂等回放及 revision INSERT；同时防止 entry 元数据在回放中丢失。兼容历史 NULL，删 continuous 确认后的重复维度 UPDATE，保持事务、整份冻结确认、主体独立和记忆/outbox 一致。

可行性：复用已有字段、服务、事务和测试夹具，无新增表/迁移、接口、功能、依赖、中间件或框架；只有测试证据充分的小步进入实现。

后续只计划：拆 profile.py 的草稿装载/协商、revision writer、授权删除/恢复及 handler；按明确用途收敛投影读取。旧协议兼容结束、普通海报和知遇入口取舍等待产品决定，本批不删旧协议或历史资料，不合并双主体确认。

验证：mock provider + testing + 不可达本机数据库/Redis端口，运行定向 pytest、实际消费者安全用例、Ruff、compileall；真实库仅使用确认隔离的临时 MySQL/Redis。全仓/CI 的无关基线失败如实列出。本批不合并、不部署、不操作生产数据。

实际结果、提交和关联 PR 在验证记录中补充。
