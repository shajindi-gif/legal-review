# 07 数据分析与埋点方案（Analytics Plan）

> 选型结论：**自建轻量事件表（Postgres）起步，不引入第三方统计**。理由：① 政务场景敏感，第三方 SDK（GA/PostHog Cloud）数据出境与合规审查成本高；② 后端已有 structlog+Prometheus+agent_logs 基建，事件表边际成本≈0；③ 用户量级（初期百级）不需要 ClickHouse 级方案。后期如需会话回放/热力图，再评估 Umami 自部署（隐私友好）。

---

## 1. 指标体系（北极星：周完成审查文件数）

| 层 | 指标 | 定义 | 数据源 |
| --- | --- | --- | --- |
| 获取 | Visitor UV | 每日独立访客 | nginx 日志/前端 PV 事件 |
| 获取 | 访问→注册转化率 | signup/UV | events |
| 激活 | **首次任务完成率** | 注册 72h 内完成 ≥1 次审查 | events+tasks |
| 激活 | 激活定义 | 完成 2 次审查（=用完免费额度，验证价值闭环） | tasks |
| 转化 | 免费→付费转化率 | 首单支付成功/注册 | orders |
| 转化 | 定价页→下单转化率 | create_order/定价页 UV | events+orders |
| 留存 | D7 复访率、周活跃用户（完成审查口径） | tasks/users | events+tasks |
| 收入 | MRR、ARPU、ARPPU | 订阅口径 | orders+user_plans |
| 成本 | **单次审查 LLM 成本** | Σ(tokens×刊例价)/审查次数 | agent_logs.usage |
| 健康 | 429 触发数→升级弹层打开率→下单率 | 付费墙漏斗 | events |

低频产品注意：不用 DAU/MAU 套壳，以「周审查文件数」「档案回访率」为主健康指标。

## 2. 事件表设计（P0 落地范围）

```sql
CREATE TABLE analytics_events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id UUID NULL,                -- 未登录为 NULL
    anonymous_id VARCHAR(64) NULL,    -- 前端生成，注册后绑定
    session_id VARCHAR(64) NULL,
    event VARCHAR(64) NOT NULL,       -- 见事件字典
    properties JSONB NOT NULL DEFAULT '{}',
    page VARCHAR(128) NULL,
    referrer VARCHAR(256) NULL,
    ua VARCHAR(256) NULL,
    ip_hash VARCHAR(64) NULL          -- sha256(ip+salt) 前 16 位，仅反作弊
);
CREATE INDEX idx_ae_event_time ON analytics_events(event, created_at);
CREATE INDEX idx_ae_user_time ON analytics_events(user_id, created_at);
```

**隐私最小化**（个保法）：不存明文 IP/手机号/邮箱/文件内容；properties 只存业务枚举与 ID；埋点清单在隐私政策中披露。

## 3. 事件字典（最小可用集，P0 先埋 10 个）

| 事件 | 触发点 | 关键属性 |
| --- | --- | --- |
| page_view | 前端路由变化 | path |
| pricing_view | /pricing 曝光 | source: direct/landing/paywall |
| signup_submit | 注册提交成功 | method: email |
| first_task_started | 首次点上传/开始审查 | is_first_task |
| task_completed | 审查任务成功 | task_id, duration_s, plan_tier |
| quota_exhausted | 收到 429 | free_used, free_limit |
| upgrade_dialog_view | 升级弹层曝光 | trigger: 429/usage_card |
| upgrade_click | 弹层点「升级」 | plan_tier |
| order_created | POST /orders 成功 | plan_tier, period_days, channel, amount_cents |
| order_paid | 回调支付成功 | order_id, amount_cents |

前端埋点：一个 `track(event, props)` util（fetch sendBeacon 到 `POST /api/v1/analytics/events`，fire-and-forget）；后端埋点：order_paid/task_completed 在服务端事务后写 events（防前端丢失）。

## 4. 报表口径（首版手工 SQL，不出 BI）

- 漏斗日报：UV → pricing_view → signup → first_task → order_paid
- 付费墙漏斗：quota_exhausted → upgrade_dialog_view → upgrade_click → order_created → order_paid
- 成本周报：单次审查 tokens 分布与 ¥ 成本（agent_logs join 刊例表）

## 5. 实施与验收

- Sprint C1：建表迁移 + 后端 events 路由 + 前端 track util + 10 事件埋点 + 3 条 SQL 报表
- 验收：注册→免费 2 次→429→弹层→下单全链路在 events 表可回放；埋点延迟 <5s；无 PII 落库
- 不做：A/B 平台（先人工对比）、归因模型（last-touch 足够）
