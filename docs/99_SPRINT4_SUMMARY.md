# Sprint 4 阶段性总结 · Agent 节点编排与 LLM Gateway 交付

> 交付日期：2026-08-22
> 阶段：Sprint 4（Agent 节点编排 + Prompt 版本化 + LLM Gateway + Supervisor 路由）
> 状态：✅ 后端核心完成，待真实 LLM API 联调 + Golden Dataset 评测

---

## 1. 交付物清单

| 类别 | 文件 | 说明 |
|------|------|------|
| LLM Gateway | [app/tools/llm.py](file:///Users/shajindi/traework/legal-review/backend/app/tools/llm.py) | DeepSeek-V4-Pro/Flash + Qwen3.7-Max/Plus/Turbo + Mock 可切；指数退避重试 + 令牌桶限流 + JSON Mode |
| Prompt 版本管理 | [app/services/prompt_manager.py](file:///Users/shajindi/traework/legal-review/backend/app/services/prompt_manager.py) | YAML 双源 + registry 激活层 + Jinja2 渲染 + 评估门控（≥90%）+ DB 同步 |
| Prompt 模板 | [app/agent/prompts/](file:///Users/shajindi/traework/legal-review/backend/app/agent/prompts) | 8 个 Prompt v1.0.0：doc_classify / legal_query / authority / procedure / content / risk / evidence_verify / report_generation |
| Tool Registry | [app/tools/registry.py](file:///Users/shajindi/traework/legal-review/backend/app/tools/registry.py) | 9 个工具注册：ocr/docx/pdf/txt 解析 + structure_extractor + rag_search + llm_complete + prompt_manager |
| Security Harness | [app/agent/harness.py](file:///Users/shajindi/traework/legal-review/backend/app/agent/harness.py) | 节点白名单 + Supervisor 路由表 + State 不变量校验 + audit_log + security_checked 装饰器 |
| LangGraph 工作流 | [app/agent/graph.py](file:///Users/shajindi/traework/legal-review/backend/app/agent/graph.py) | 11 节点 + 3 条件路由（classify_router / authority_router / evidence_verify_router）+ Retry Edge |
| Agent 节点 | [app/agent/nodes.py](file:///Users/shajindi/traework/legal-review/backend/app/agent/nodes.py) | 全部 11 节点实现：_run_llm_node 统一入口 + LLM JSON Mode + EvidenceHarness 双校验 |
| 全局配置 | [app/core/config.py](file:///Users/shajindi/traework/legal-review/backend/app/core/config.py) | DeepSeek-V4/Qwen3.7 四档模型（strong/balanced/flash/reasoner）+ 重试/限流参数 |
| 单元测试 | tests/test_graph.py / test_harness.py / test_prompt_manager.py / test_llm.py / test_registry.py / test_nodes_report_generation.py | 6 个测试文件，覆盖 Sprint 4 全部模块 |

---

## 2. 质量门控结果

| 门控 | 命令 | 结果 |
|------|------|------|
| Python 语法 | `python -m compileall app tests` | ✅ 0 错误 |
| Ruff Lint | `ruff check app/ tests/` | ✅ All checks passed |
| 单元测试 | `pytest tests/` | ✅ 234 passed in 2.01s |
| 代码覆盖率 | `pytest --cov` | ✅ 81%（Sprint 4 核心模块 ≥ 93%） |

Sprint 4 模块覆盖率明细：
- `app/tools/llm.py` 98%
- `app/services/prompt_manager.py` 93%
- `app/tools/registry.py` 96%（get_tool 反射加载路径 1 行未覆盖）

Sprint 4 测试覆盖：
- `test_graph.py`：条件路由（classify/authority/evidence_verify）、Retry Edge、iteration 自增、超限兜底
- `test_harness.py`：State 不变量校验、节点白名单、路由表越权拦截、EvidenceHarness enforce_silent
- `test_prompt_manager.py`：registry 加载、版本管理、Jinja2 渲染、StrictUndefined、评估门控、DB 同步
- `test_llm.py`：Provider 切换、_resolve_model 四档路由、重试指数退避、令牌桶限流、JSON Mode
- `test_registry.py`：list_tools、get_tool 已注册/未注册/版本校验、ToolSpec frozen 不可变
- `test_nodes_report_generation.py`：证据收集、LLM 成功/失败、prompt_versions 写入、4 Agent 结果传入

---

## 3. 核心设计落地

### 3.1 LLM Gateway 多 Provider 可切（FR-016）

| 档位 | DeepSeek | Qwen | 适用场景 |
|------|----------|------|---------|
| strong（旗舰） | deepseek-v4-pro | qwen3.7-max | 主体审查/内容审查/证据校验（高准确率） |
| balanced（速度） | deepseek-v4-flash | qwen-plus | 程序审查/报告生成（中等复杂度） |
| flash（轻量） | deepseek-v4-flash | qwen-turbo | 文件分类/query 生成（轻量快速） |
| reasoner（推理链） | deepseek-v4-pro | qwen3.7-max | 风险评级（综合推理） |

- **切换**：`LLM_PROVIDER` 环境变量 + `get_llm_provider()` 工厂
- **模型路由**：`_resolve_model(model, tier)` 按档位映射到具体模型名
- **重试**：指数退避（基数 2s，最多 3 次），仅重试可重试异常
- **限流**：令牌桶（默认 60 RPM），超限等待而非拒绝
- **JSON Mode**：`complete_json()` 强制结构化输出，解析失败抛 AgentError

### 3.2 Prompt 版本化（FR-016）

- **双源架构**：YAML 文件（模板 + 变量定义）+ registry.yaml（激活版本 + 模型路由 + 评估门控）
- **模型路由统一**：YAML 不再硬编码 model_name，registry.yaml 为唯一真相源（支持模型代际升级零改动切换）
- **渲染**：Jinja2 + StrictUndefined（缺失变量直接报错，不静默渲染空值）
- **评估门控**：`activate()` 前检查 `min_eval_pass_rate`（默认 ≥ 90%），不达标拒绝激活
- **DB 同步**：`sync_to_db()` 将 YAML 版本写入 `prompts` 表，支持线上回滚
- **8 个 Prompt**：覆盖全审查链路，每个含 model_tier + temperature + min_eval_pass_rate

### 3.3 Tool Registry 强校验（硬约束#3）

- **9 个工具**：ocr_tool / ocr_pdf / docx_parser / pdf_parser / txt_parser / structure_extractor / rag_search / llm_complete / prompt_manager
- **反射加载**：`get_tool(name, version)` 通过 importlib 动态加载，未注册抛 ValidationError
- **版本锁定**：支持版本号校验，防止调用过期工具
- **ToolSpec 不可变**：frozen dataclass，运行时不可篡改

### 3.4 Security Harness 与 Supervisor 路由

- **节点白名单**：12 个允许节点（11 Agent 节点 + END），白名单外禁止路由
- **路由表**：`SUPERVISOR_ROUTE_TABLE` 定义每个节点的合法下一跳集合，越权抛 ValidationError
- **State 不变量**：trace_id / task_id / iteration / max_iteration / prompt_versions 必填校验
- **security_checked 装饰器**：包裹所有 Agent 节点，入口/出口双审计 + 异常捕获审计

### 3.5 LangGraph 工作流编排

```
START → doc_parse → doc_classify
                       ├─(normative)→ legal_retrieve → authority_review
                       │                                ├─(pass)→ procedure_review → content_review
                       │                                │            → risk_assessment → evidence_verify
                       │                                └─(fail)→ report_generation
                       └─(non-normative)→ report_generation
         evidence_verify ├─(pass)→ report_generation → human_review → END
                         ├─(retry, iter<max)→ legal_retrieve（Retry Edge）
                         └─(fail, iter≥max)→ human_fallback → human_review → END
```

- **3 个条件路由**：classify_router（是否规范性文件）/ authority_router（主体是否合法）/ evidence_verify_router（证据是否完整 + 迭代上限）
- **Retry Edge**：evidence_verify 失败且未超限时回到 legal_retrieve 重新检索
- **迭代上限**：默认 5 次，超限走 human_fallback 兜底

### 3.6 Agent 节点统一 LLM 流程

`_run_llm_node()` 统一入口：
1. `get_prompt_manager().render()` 渲染 Prompt（Jinja2 + StrictUndefined）
2. `get_llm_provider().complete_json()` 调 LLM（JSON Mode + 重试 + 限流）
3. 构造 `AgentOutput`（node_status / confidence / raw_json / duration_ms / iteration）
4. 写入 `prompt_versions[agent_name]`（硬约束：每个节点记录 Prompt 版本号）
5. 更新 `ReviewTask` 任务状态（current_node + status）
6. LLM 异常 → `node_status=RETRY`（不中断工作流，由路由器决定重试或兜底）

### 3.7 证据引用强校验（EvidenceHarness）

- `evidence_verify_node` 合并 4 个 Agent 输出，调 LLM 校验证据完整性
- `EvidenceHarness.enforce_silent()` 双重校验：每条 RiskItem 的 Evidence 必须含 law_name + article + original_text
- 缺字段 → `node_status=RETRY` → 触发 Retry Edge 回到 legal_retrieve

### 3.8 审核意见草稿（report_generation）

- 收集 4 个 Agent 输出的全部 evidences（去重法规引用）
- 构建 7 变量 Prompt（doc_info / overall_status / 4 个 Agent 结果 / all_evidences）
- LLM 生成 7 章节结构化报告：文件基本情况 / 审查依据 / 审核过程 / 发现问题 / 风险等级 / 修改建议 / 审查意见
- 硬约束：「审查依据」必须列出全部引用法规；「审查意见」必须含人工复核栏占位

---

## 4. 硬约束落地

| 硬约束 | Sprint 4 落地位置 |
|--------|------------------|
| Agent 五可（评估/追溯/迭代/扩展/商业化） | 全节点输出 AgentOutput 含 trace_id/iteration/version；LLM Provider 可插拔；Prompt 版本可回滚 |
| Prompt 版本化 + 不硬编码 | 8 个 YAML + registry.yaml 激活层；YAML 不含 model_name（registry 统一管理） |
| 未注册工具禁调 | ToolRegistry.get_tool() 强校验，9 个工具注册 |
| Agent 循环上限 | evidence_verify_router 迭代 ≤ 5，超限走 human_fallback |
| 安全节点不可绕过 | SecurityHarness 路由表 + security_checked 装饰器 + State 不变量 |
| 所有判断附法规依据 | EvidenceHarness.enforce_silent 校验 law_name + article + original_text |
| 未经评估的 Prompt 变更禁止合并 | PromptManager.activate() 评估门控 ≥ min_eval_pass_rate |
| 版本号管理 | ToolSpec.version + PromptSpec.version + AgentOutput.iteration |

---

## 5. 关键问题与修复

| 问题 | 根因 | 修复 |
|------|------|------|
| `ModuleNotFoundError: No module named 'langgraph'` | 虚拟环境缺包 | pyproject.toml 添加 `langgraph>=0.2.0` + `pip install .` |
| `LLMProvider.complete_json() got unexpected keyword 'tier'` | 接口未声明 tier 参数 | 在 complete_json / complete 方法签名添加 `tier` 参数并透传 |
| Prompt YAML 硬编码 `model_name: deepseek-chat`（已停用熔断） | YAML 与 registry 双源，YAML 优先级高导致用旧模型 | 移除 8 个 YAML 的 model_name，registry.yaml 为唯一真相源 |
| `.env` 覆盖 config.py 默认值用旧模型 | DEEPSEEK_MODEL_STRONG=deepseek-chat / QWEN_MODEL_STRONG=qwen2.5-72b | .env 更新为 deepseek-v4-pro / qwen3.7-max |
| `AgentError.__init__() missing 'message'` | AgentError 需要 (agent, message) 双参数 | 测试修正调用签名 |
| Ruff E501 行过长 | model_name 回退链单行 | 拆多行括号表达式 |
| Ruff B017 盲异常捕获 | `pytest.raises(Exception)` | 改用 `FrozenInstanceError` 精确捕获 |
| test_legal_retrieve 断言失败 | LLM mock 未注入导致走启发式路径 | patch get_llm_provider 强制异常走兜底 |

---

## 6. 模型版本对齐（用户指令）

> 用户指令："gateway deepseek qianwen 都更新到多少代了，用最新版本两三代以内的 flash pro 等等"

截至 2026-08-22 最新版本核实：

| 厂商 | 最新代 | 旗舰模型 | 轻量模型 | 本系统使用 |
|------|--------|---------|---------|-----------|
| DeepSeek | V4（2026-07/08） | deepseek-v4-pro（0813 正式版） | deepseek-v4-flash（0731 正式版） | ✅ V4-Pro + V4-Flash |
| Qwen | Qwen3.7（旗舰 API）/ Qwen3.8（开放权重） | qwen3.7-max（MoE 旗舰） | qwen-turbo | ✅ Qwen3.7-Max + Qwen-Plus + Qwen-Turbo |

均在最新两三代以内，符合用户要求。

---

## 7. Sprint 4 剩余工作

| 任务 | 状态 | 说明 |
|------|------|------|
| Agent 节点编排 + Prompt + LLM + Registry + Harness | ✅ | 本文档 |
| 单元测试（6 模块） | ✅ | 234 tests passed, 81% coverage |
| Ruff Lint | ✅ | All checks passed |
| 真实 LLM API 联调 | ⏳ | 需配置 DEEPSEEK_API_KEY / QWEN_API_KEY，跑端到端审查流程 |
| Golden Dataset 评测 | ⏳ | 8 个 Prompt 各需 ≥ 50 条标注样本，通过率达标后激活 |
| Prompt A/B 评测 | ⏳ | DeepSeek-V4-Pro vs Qwen3.7-Max 在审查任务上的准确率对比 |
| 前端审查工作台 | ⏳ | Next.js + Three.js，Sprint 7 交付 |

---

## 8. 启动方式

```bash
# 1. 启动依赖
cd /Users/shajindi/traework/legal-review
docker compose up -d postgres redis

# 2. 后端
cd backend
.venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env  # 填入 DEEPSEEK_API_KEY / QWEN_API_KEY
alembic upgrade head

# 3. 跑测试
.venv/bin/python -m pytest

# 4. 启动 API
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
# 文档：http://localhost:8000/docs
```

---

## 9. Sprint 5 启动条件

### 9.1 已具备

- ✅ LLM Gateway 多 Provider 可切（DeepSeek-V4 + Qwen3.7 + Mock）
- ✅ Prompt 版本化（8 个 YAML + registry + 评估门控 + DB 同步）
- ✅ Tool Registry 强校验（9 个工具注册）
- ✅ Security Harness（路由表 + 节点白名单 + State 不变量 + 审计）
- ✅ LangGraph 工作流（11 节点 + 3 条件路由 + Retry Edge）
- ✅ Agent 节点全部实现（_run_llm_node 统一入口 + EvidenceHarness 双校验）
- ✅ 审核意见草稿生成（report_generation 7 章节模板）

### 9.2 Sprint 5 待实现

1. **评测体系落地**：Golden Dataset 标注 + Prompt 评估管线 + A/B 测试框架
2. **端到端集成测试**：真实法规导入 → 审查全流程 → 报告输出
3. **人工复核闭环**：human_review 反馈写入 + Feedback Loop 案例管理
4. **法规库更新循环**：定期法规时效检查 + 自动状态变更
5. **可观测性**：trace_id 全链路追踪 + Agent 节点耗时/置信度监控

---

**Sprint 4 Agent 节点编排与 LLM Gateway 交付终止。下一步：配置真实 API Key 跑端到端审查流程，或进入 Sprint 5 评测体系与人工复核闭环。**
