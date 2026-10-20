# LegalAI 86 /「智审 · LegalReview」合规说明

> 仓库：`legal-review` ｜ 分支：`upgrade/legalai86-platform` ｜ 品牌：智审 · LegalReview
> 经营主体：上海衍策引擎人工智能科技有限公司（`frontend/src/lib/site.ts`）
> 文档性质：**工程侧合规现状自述**，逐项以仓库代码为证据。**本文件不构成法律意见**；正式合规结论须经运营方与法律专业人员确认后方可对外使用。
> 编制日期：2026-10-20。
> 引用约定：以下路径均为仓库相对路径；凡标注「未核实 / UNKNOWN / 目标值」的项，均**未**通过代码或生产验证，不得据此对外宣称已达成。

---

## 1. 合规范围与原则

本产品面向「行政规范性文件智能合法性审查」与「法律研究工作台」，输出为 **AI 辅助结果**，非法定结论。合规建设遵循以下可核验原则：

| 原则 | 落地机制（代码证据） |
|------|----------------------|
| 不编造引用 | `backend/app/services/citation_verifier.py` 四要素核验，未通过即返回明确状态 |
| 不宣称未核实的授权 | `legal_sources.authorization_status` 默认 `unknown`（`backend/app/models/legal.py:99-129`） |
| 生成内容免责标识 | `backend/app/schemas/gov_review.py:29-34` 的 `DISCLAIMER` 与 `MISSING_MATERIAL_NOTE` |
| 最小必要收集 / 个人信息保护 | 隐私政策页 + 密码加密存储（见 §3） |
| 多租户数据隔离 | `organization_id` + `backend/app/services/tenant.py`（见 §6） |
| 全链路可追溯 | `backend/app/services/audit.py` 审计 + `trace_id`（见 §9） |
| 诚实红线 | 无真实客户不展示假案例；未实现的模块置 `comingSoon`（`docs/CHANGELOG_LEGALAI86.md`） |

---

## 2. 数据来源合规

### 2.1 登记与授权状态机制（已核实的代码约束）

- 数据源登记表 `legal_sources`（`backend/app/models/legal.py:99-129`）逐源记录：`base_url` / `domain` / `robots_checked_at` / `terms_url` / `authorization_status` / `enabled` / `notes`。
- 状态枚举 `SourceAuthorizationStatus`（`backend/app/core/constants.py:319-325`）：`verified` / `restricted` / `prohibited` / `unknown`。
- **默认值约束**：`authorization_status` 字段 `default=SourceAuthorizationStatus.UNKNOWN`，`enabled` 字段 `default=False`（`legal.py:118-121`）。即**未逐源核实前，数据源一律为 `unknown` 且默认不启用**。
- 模型注释明确写入硬约束：「`authorization_status` 未核实前一律 UNKNOWN，禁止宣称 READY」（`legal.py:102-104`）。

### 2.2 当前状态（如实陈述）

- 逐源核实流程（robots.txt / 使用条款 / 授权）为**流程性要求**，具体抓取适配器尚未实现。
- 据 `docs/CHANGELOG_LEGALAI86.md`「未完成项」：「数据源适配器：需逐源核实 robots.txt / 使用条款 / 授权后再实现抓取，未核实前 `legal_sources.authorization_status` 保持 `unknown`，不得宣称 READY。」
- **结论**：当前无任何数据源被标注为可合规访问并启用；抓取能力未落地，**不存在绕过访问控制（bypass）的抓取实现**。

> 状态：**未核实 / 未实现**（不得宣称数据源授权已就绪）。

---

## 3. 个人信息与隐私

### 3.1 隐私政策与披露

- 隐私政策页：`frontend/src/app/privacy/page.tsx`（说明收集范围：账号信息、验证信息、业务内容、使用与设备信息、订单信息）。
- 服务条款页：`frontend/src/app/terms/page.tsx`（含「AI 辅助性质与免责说明」）。
- Cookie 政策页：`frontend/src/app/cookies/page.tsx`。
- 三页统一由 `frontend/src/components/legal/policy-shell.tsx` 渲染；当经营主体信息未填写时，页面顶部展示草稿提示：「本页面为待审阅草稿……正式对外发布前须由运营方核对并补充，且需经法律专业意见审核」（`policy-shell.tsx:41-46`）。

### 3.2 凭证保护

- 密码以加密形式存储、不以明文保存（隐私政策页声明）；后端密码散列依赖 `bcrypt` / `argon2-cffi`（`backend/pyproject.toml:51-54`）。
- 「账户锁定」（`failed_login_count` / `locked_until`）整改台账标注为 **待整改**（`docs/rectification/00_ISSUE_REGISTER.md` R2-1），即暴力破解防护目前**部分缺失**。

### 3.3 待补充的合规字段（阻塞项，需运营方提供）

据 `frontend/src/lib/site.ts:11-23` 与整改台账 R1-4，以下字段为空或占位，代码无法代填：

- 统一社会信用代码（`unifiedSocialCreditCode: ""`）
- 办公地址（`officeAddress: ""`）
- 公安备案号（`icpSecurityRecord: ""`）
- 政策生效日（`policyEffectiveDate: ""`）

> 状态：隐私政策/条款/Cookie 页**已存在**（可核实）；合规落款字段**空缺、待运营方补充**。

---

## 4. 内容安全与生成内容标识

- 所有规范性审核输出强制附免责声明：`DISCLAIMER = "以上均为 AI 辅助审查结果，不代表法定审核机构作出的正式结论；正式合法性审核意见必须经过有权人员审核确认。"`（`backend/app/schemas/gov_review.py:29-32`），并作为默认字段挂在报告模型上（`gov_review.py:208`）。
- 报告导出层在标题中显式标注「AI 辅助」：
  - Markdown 报告标题：「规范性文件合法性审核意见（AI 辅助初稿）」并追加 `> {DISCLAIMER}`（`backend/app/services/gov_review_report.py:330,367`）。
  - 导出报告标题：「规范性文件合法性审核报告（AI 辅助）」（`backend/app/services/gov_export.py:36`）。
- 待人工核实项统一标注理由「AI 辅助审查结果，须由有权人员核实后确认」（`gov_review_report.py:290`）。
- **程序材料缺失的诚实处理**：`MISSING_MATERIAL_NOTE = "程序材料尚未提供：仅标记为「材料不足」，不据此认定程序违法。"`（`gov_review.py:34`），缺失材料项与待办项均引用该说明（`gov_review_report.py:254,304`）。即**不因材料缺失而推定程序违法**。

> 状态：**已核实**（生成内容标识与免责声明在模型层与导出层均已落地）。

---

## 5. AI 输出免责与「不编造引用」机制

### 5.1 法律依据核验引擎

`backend/app/services/citation_verifier.py` 对每条法律依据做**四要素逐项核验**：法规名称 / 条款编号 / 引用原文 / 时效。设计原则（文件头注释）明确：

1. 四要素任一不通过即**不可宣称「已核实」**；
2. **不做「文本相似度即法律效力」的混淆**——相似度仅用于判断引用原文是否吻合；
3. 无法核验时返回明确状态 + 统一提示。

### 5.2 统一不可核验提示

`CANNOT_VERIFY_MESSAGE = "暂未找到可核验的权威依据，需要人工复核。"`（`backend/app/schemas/citation.py:31`）。该提示在法规不存在、条款不存在、原文不一致、时效失效等多条失败路径上返回，且默认 `needs_human_review=True`（`citation_verifier.py:280-378,417-444`）。

### 5.3 判定细节（可离线单测的确定性算法）

- 名称匹配下限 `_LAW_NAME_MIN_SIMILARITY = 0.85`；原文「吻合」下限 `0.999`（exact）、`0.90`（near）（`citation_verifier.py:37-40`）。
- 时效判定 `classify_validity`：废止/过期/草案/未生效/时效外 → 不通过（`citation_verifier.py:148-170`）。
- 核验核心**不依赖 LLM**，`LawLookup` 抽象可注入假实现做离线单测（`citation_verifier.py:212-266`）。

> 状态：**已核实**（机制存在且由 `backend/tests/test_citation_verifier.py` 覆盖；具体准确率指标见 `docs/BENCHMARK.md`，**尚未评测**）。

---

## 6. 多租户与数据隔离

- 隔离实现为**应用层强制**：`WHERE organization_id = current_user.organization_id`（显式不引入 PostgreSQL RLS，见 `backend/app/services/tenant.py:1-15`）。
- 核心函数：`apply_org_filter_with_column()`（`tenant.py:118-141`）——`super_admin` 不过滤；团队组织按 `org_column == organization_id` 过滤；个人虚拟组织回退 `user_id_column == user.id` 单租户隔离。
- 任务查询接入：`backend/app/api/v1/tasks.py` 的 `_filter_by_tenant()` / `_can_view_all()`（`tasks.py:45-60`）。
- 隔离冒烟脚本：`backend/scripts/verify_tenant_isolation.py`——创建任务后用第二账号登录，断言「另一用户看不到该 task（隔离生效）」，退出码 0=PASS、1=FAIL、2=SKIP。

### 待整改项

据整改台账 R2-2：「多租户隔离仅覆盖 tasks + documents，`notifications` / `feedback` 未接入」（`docs/rectification/00_ISSUE_REGISTER.md`）。

> 状态：任务/文档隔离**已实现并带冒烟脚本**；通知/反馈表隔离**待整改**。跨组织泄露指标见 `docs/BENCHMARK.md`（**0 为目标值，尚未评测**）。

---

## 7. 文件安全与沙箱

`backend/app/services/sandbox.py` 落实「Security Harness」硬约束：

| 控制项 | 实现 | 证据 |
|--------|------|------|
| 路径防逃逸 | `resolve()` 后必须收敛在 `sandbox_root` / `task_dir` 内；含 `..` 直接拒绝 | `sandbox.py:42-83` |
| 任务级隔离 | 目录结构 `{sandbox_root}/{task_id}/`，跨任务读取失败 | `sandbox.py:26-33,140-145` |
| 文件名 sanitize | 禁 `/ \ : * ? " < > \| \0` 及控制字符 | `sandbox.py:22,62-83` |
| 扩展名白名单 | `docx,pdf,png,jpg,jpeg,txt` | `backend/app/core/config.py:40`, `sandbox.py:86-91` |
| 大小限制 | `sandbox_max_file_mb = 50` | `config.py:39`, `sandbox.py:93-99` |
| 内容指纹 | SHA-256（字节 / 流式） | `sandbox.py:152-165` |
| 路径不外泄 | DB 仅存沙箱内相对路径 | `sandbox.py:128-131` |

上传流程按「sanitize → 扩展名 → 大小 → 路径解析」顺序校验（`sandbox.py:102-131`），由 `backend/tests/test_sandbox.py` 覆盖（含拒 `.exe`/`.js`、超限、`../../etc/passwd`、跨任务访问、Hash）。

> 状态：**已核实**（代码 + 单测存在）。存储为本地沙箱 + Docker volume，**非 S3 兼容对象存储**（`docs/LEGALAI86_AUDIT.md` 审计项 #11）。

---

## 8. 密钥与凭证管理

- 所有密钥/凭证均走环境变量，未在代码中硬编码明文密钥：`backend/app/core/config.py` 定义 `deepseek_api_key` / `qwen_api_key` / `dashscope_api_key` / `jwt_secret` / `alipay_private_key` / `wxpay_*` / 短信与邮件密钥等字段（`config.py:50-177`），取值来自 env（`backend/.env.example`）。
- 支付凭证通过脚本安装：`deploy/scripts/install-payment-env.sh`。
- `jwt_secret` 存在**开发默认值** `"change_me_in_production"`（`config.py:84`）——生产必须以真实值覆盖（部署 env 文档已提示，但**生产实际取值 UNKNOWN**，`docs/LEGALAI86_AUDIT.md` 审计项 #18）。
- **日志脱敏现状（注意项）**：`backend/app/core/logging.py` 仅做 JSON 结构化与 `trace_id` 注入，**未见对密钥/令牌的脱敏处理器**；因此「密钥不入日志」依赖调用方自觉，属**弱保障**，建议后续补脱敏 processor。

> 状态：密钥**未硬编码**（可核实）；`jwt_secret` 开发默认值需生产覆盖；日志脱敏**未实现**（注意项）。

---

## 9. 审计与可追溯

- 审计服务 `backend/app/services/audit.py`：`AuditService.log()` 写入 `audit_records`，字段含 `trace_id` / `actor_id` / `actor_role` / `action` / `target_type` / `target_id` / `before_value` / `after_value` / `ip_address` / `user_agent`；文件头注明「合规要求保留 3 年」。
- 审计动作枚举 `AuditAction`（`backend/app/core/constants.py:221-227`）：`create` / `upload` / `review` / `modify` / `sign` / `delete`。
- 评测与反馈 API 已接入审计：Golden Case 与评测运行均写审计（`backend/app/api/v1/eval.py:106-114,131-142,216-228`）。
- 涉密例外：测试中 `AuditService.log` 被自动桩为 no-op（`backend/tests/conftest.py:28-36`），仅影响测试环境，不影响生产。

> 状态：**已核实**（审计写入链路存在；「保留 3 年」为设计要求，实际留存策略需生产侧确认）。

---

## 10. 域名 / 备案 / ICP 现状

### 10.1 唯一合法域名

据 `docs/LEGALAI86_AUDIT.md` §0.1（只读探测）：

- `legalai86.com.cn`：DNS 解析到 `124.221.229.12`，`https://legalai86.com.cn/health` 返回 **200** → **当前真实生产域名**。
- `legal86.com.cn`：**无 DNS 记录、无法解析** → 未接入。
- 代码/配置中生产绑定全部指向 `legalai86.com.cn`：后端 `public_base_url`、CORS（`deploy/.env.example:19`）、nginx `server_name`（`deploy/nginx/conf.d/legalai86.com.cn.conf:22`）、前端 `frontend/next.config.mjs:25-26`。

**结论**：`legal86.com.cn` 与 `legalai86.com.cn` **不是同一域名**；前者当前未接入，未对其做任何 DNS / 备案 / 绑定变更。

### 10.2 ICP 备案

- 前端展示备案号：`沪ICP备2026045851号-4`（`frontend/src/lib/site.ts:15`，运营方 2026-10-15 提供），并在页脚链接至 `beian.miit.gov.cn`（`policy-shell.tsx:57-68`）。
- **不一致（待整改）**：`deploy/.env.example:55-57` 仍为占位值 `京ICP备 0000000 号-1` / `京公网安备 11010100000000 号`。部署环境变量须替换为真实备案号，否则与前端展示不一致。
- 公安备案号：`icpSecurityRecord: ""`，**待补**。

> 状态：域名唯一且已备案（前端展示可核实）；部署占位备案号与公安备案号**待更新/待补**。

---

## 11. 支付合规

- 真实订单闭环已上线（`docs/LEGALAI86_AUDIT.md` 审计项 #7）：支付宝 `page.pay` / `wap.pay`，**下单 + 回调验签 + 幂等结算 + 退款**。
- 业务层 `backend/app/services/payment/service.py`：
  - 幂等回调（文件头职责划分注明「幂等」）；
  - `refund_order()` 支持**部分退款**，退款金额不得超过「实付 − 历史已退」，退款流水一笔一条落库，全额退清后回收套餐权益（降回 Free 并置 cancelled）（`service.py:516-631`）。
  - pending 订单超 120 分钟自动关闭（`service.py:37`）。
- 渠道限制：当前**仅支付宝可用**；微信 V3 已实现但 `wxpay_enabled` 默认 `false`（`config.py:158`），需商户资质后开启。部署侧有专门「支付宝专用」验收：`deploy/scripts/verify-alipay-only.sh` 与 `ALIPAY_ONLY=1` 跳过 `WXPAY_*` 校验（`deploy/scripts/install-payment-env.sh:35-55`）。
- **发票系统 MISSING**：代码库无发票模型/接口（`docs/LEGALAI86_AUDIT.md` 审计项 #8），属商业化关键缺口。

> 状态：支付宝真实闭环**已核实**；微信未启用；发票能力**未实现**。

---

## 12. 未决合规事项与阻塞项

| # | 事项 | 证据 | 状态 |
|---|------|------|------|
| C1 | 数据源逐源核实（robots/条款/授权）与抓取适配器 | `legal.py:99-129`、`CHANGELOG_LEGALAI86.md` 未完成项 | **未实现 / 未核实**（`authorization_status` 一律 `unknown`） |
| C2 | 统一社会信用代码 / 办公地址 / 公安备案号 / 政策生效日 | `frontend/src/lib/site.ts:11-23`、整改台账 R1-4 | **阻塞：需运营方提供** |
| C3 | 部署环境备案号为占位值 | `deploy/.env.example:55-57` | **待替换** |
| C4 | notifications / feedback 未纳入多租户隔离 | 整改台账 R2-2、`tenant.py` | **待整改** |
| C5 | 账户锁定（失败登录计数/锁定时间）未接线 | 整改台账 R2-1 | **待整改** |
| C6 | 日志无密钥/令牌脱敏处理器 | `backend/app/core/logging.py` | **注意项 / 待补** |
| C7 | `jwt_secret` 开发默认值需生产覆盖 | `config.py:84` | **部署约束** |
| C8 | 发票系统缺失 | 审计项 #8 | **未实现** |
| C9 | 规则包 `legal_review_status: pending_legal_review`、条号/生效日待专业核实 | `docs/CHANGELOG_LEGALAI86.md` PHASE 1-5 | **待专业人员审核** |

> **重要声明**：上述 C1–C9 中任何一项在完成核实/整改前，**不得对外宣称已合规就绪**。涉及评测指标的内容见 `docs/BENCHMARK.md`，其中首期验收目标均为**未评测的目标值**。

---

**本合规说明终止。** 本文件仅陈述截至 2026-10-20 的代码级现状，不含法律意见；正式合规发布须经运营方与法律专业人员确认。
