# 实现报告

## 规格与任务范围

- 规格：`1.1/通用写作智能体评测体系重构`
- 本轮任务：12.4
- 需求映射：15.14—15.18、15.23、15.25、15.33—15.40
- 设计映射：7.13、11.3、12.1—12.4、16.1—16.3
- 授权边界：恢复 DeepSeek V4 Pro 首轮；沿用同一冻结 23 案套件；禁止 fallback；只允许新增 append-only 重试；系统缺陷只分类和上报，不直接写 Inbox。

## 变更文件与职责

- `src/taichu/infrastructure/evaluations/general_agent_benchmark/live_runtime.py`
  - 新增真实模型观察网关，真实 provider 返回成功后才消费严格脚本。
  - provider 异常保持原对象和结构化摘要，不伪装成脚本失败。
  - 新增 usage/replay 转发记录器，保留每次真实调用身份、Token、费用、request ID 和错误。
  - 新增 `LiveFixtureRuntime`，复用同一密封夹具、Mongo 隔离、案例 capability exposure 和生产 Runtime 工厂，只替换模型网关与模型角色路由。
  - 构造时强制 `deepseek-v4-pro` 且 `deepseek_fallback_enabled=false`。
- `tests/unit/application/evaluations/general_agent_benchmark/test_live_runtime.py`
  - 覆盖真实响应观察、provider 异常不消费脚本、usage/replay 精确转发和禁 fallback 构造门禁。
- `tests/integration/infrastructure/evaluations/test_general_agent_benchmark_hydration.py`
  - 权威快照补充本轮最新索引直接引用的三份 append-only 工件，继续验证索引只读恢复。
- `project_assets/derived/general_agent_benchmarks/iterations/deepseek_v4_pro_20260728_nofallback_retry2.json`
  - 禁 fallback 的 RightCode 直连探测证据。
- `project_assets/derived/general_agent_benchmarks/iterations/deepseek_first_live_20260728_retry2.json`
  - 新首轮重试信封；23 案全部结构化 `blocked`，没有案例被冒充为已执行。
- `project_assets/derived/general_agent_benchmarks/iterations/deepseek_first_live_20260728_retry2_classification.json`
  - 首次生成的 provider/environment 分类；运行字段有效，但 `next_action` 经 PowerShell 管道写成问号，保留为不可变失败尝试，不再由索引引用。
- `project_assets/derived/general_agent_benchmarks/iterations/deepseek_first_live_20260728_retry2_classification_invalid.json`
  - 追加式失效声明，记录 retry2 分类的编码损坏与替代引用。
- `project_assets/derived/general_agent_benchmarks/iterations/deepseek_first_live_20260728_retry3_classification.json`
  - UTF-8 正常的 provider/environment 分类；系统问题候选为 0。
- `project_assets/derived/general_agent_benchmarks/indexes/deepseek-first-live.json`
  - 原子切换到最新重试工件，比较准入仍为 `blocked`。
- `project_assets/derived/general_agent_benchmarks/indexes/deepseek-first-live-classification.json`
  - 原子切换到 UTF-8 正常的 retry3 分类工件。

## RED / GREEN / REFACTOR / VERIFY

### RED

- 命令：`.venv\Scripts\python.exe -m pytest tests/unit/application/evaluations/general_agent_benchmark/test_live_runtime.py -q`
- 退出码：1
- 失败：`ModuleNotFoundError: ...live_runtime`
- 结论：真实 live 模型绑定不存在，符合缺失行为 RED；没有破坏已有实现制造失败。

### GREEN

- 实现真实模型观察网关、记录仓储和禁 fallback 夹具绑定。
- 定向命令：
  - `.venv\Scripts\python.exe -m pytest tests/unit/application/evaluations/general_agent_benchmark/test_live_runtime.py -q`
  - `.venv\Scripts\python.exe -m ruff check src/taichu/infrastructure/evaluations/general_agent_benchmark/live_runtime.py tests/unit/application/evaluations/general_agent_benchmark/test_live_runtime.py`
- 结果：4 passed；Ruff passed。

### REFACTOR

- 复用 `SyntheticFixtureRuntime` 的密封夹具、知识库隔离、真实 Runtime 工厂、授权层和严格观察器；未复制一套平行 23 案环境。
- 没有删除或替换旧实现；旧 synthetic 轨道和旧失败工件继续保留。

### VERIFY

- 固定端口探测：
  - `POST http://127.0.0.1:8000/api/llm/models/deepseek-v4-pro/probe` 返回 200/available。
  - 对应 usage 记录实际为 `provider=deepseek_official`、`fallback_from_provider=rightcode`、`wire_protocol=anthropic_messages`，因此不满足本轮禁 fallback 准入。
  - 固定端口最新观测 request ID：`e1d0cd1b-47e5-49a4-857d-7ff0297d1059`。
- 禁 fallback 直连：
  - `provider=rightcode`
  - `model_id=deepseek-v4-pro`
  - `wire_protocol=anthropic_messages`
  - `fallback_from_provider=null`
  - `call_id=llm-call-bcd722805e204ff39ff40f0f15c7540d`
  - `provider_request_id=null`
  - `error_code=LLM_NETWORK_ERROR`
  - Token 全部不可用；费用 `kind=unavailable`。
- 冻结结果：
  - probe hash：`350f209c9b295e011f05d3926bfe43db997637663ae20dae9bd7dfeb8c02d4a9`
  - first-live artifact ID：`first_live_1e15110e3a3619297c20988d18be5613ba12ff137be59c8414feba1fcb069ddf`
  - first-live artifact hash：`40a9eedd5cddae510396e0ce498e1823ac1ee6d9a52c034c518f0869a733ea4f`
  - 有编码缺陷且已取消索引的 retry2 classification hash：`cc736dd0cfb0bc72c804fccdb57162e73647ba62394fc7648c77b7ee24373573`
  - 当前索引的 retry3 classification hash：`30da2580752d313d3972c21f830d07d7c88fb66fd573ec30cf5a8e43e7976ddc`
  - 案例终态：23 `blocked`、0 `completed`
  - 分类：`provider_environment / execution_error`
  - `benchmark_invalid=false`
  - `system_issue_eligible=false`
  - 系统问题候选：0
  - comparison admission：`blocked`
- 不可变性：
  - 旧 envelope SHA-256 前后均为 `5dce9702f4b8d80559cf49401c3905abb31e86726711657da98053558c0efd25`
  - 旧 probe SHA-256 前后均为 `c5c7593ca455f24fd6b95383ef84d9b418e88ad3f37fd75eb9c9f0b5ec8b3b8a`
- 回归：
  - live/first-live/triage/hydration 定向：16 passed
  - 评测受影响全量：183 passed
  - Ruff：passed
  - `state.py validate`：`ok=true`

## 清理

- 没有覆盖或删除旧 error 首轮、旧 probe 或旧分类工件。
- 没有新增 fallback、假 provider、假 Tool、假 Agent 或任务专用 capability。
- 没有生成多模型比较或排名。
- 没有写入 `project_assets/source/workspace/inbox_issues.jsonl`。

## 设计偏差

- 无设计偏差。
- 23 案未发起真实 Runtime 调用的原因是禁 fallback provider 预检失败。按需求 15.33—15.40，provider 身份/fallback 准入失败必须先冻结为不可比较错误；继续调用 23 案会把同一基础设施错误放大并违反 live 准入。

## 启动与页面验证

- 后端固定端口接口已真实调用并返回。
- 本轮没有修改 `start.bat` 约束列出的启动关键文件，因此未重跑 `start.bat`。
- 本轮没有前端变更，也没有推进比较页面验收。

## 中文手动验收步骤

1. 请求 `GET http://127.0.0.1:8000/api/llm/usage/calls?page=1&page_size=5&model_id=deepseek-v4-pro`。
2. 找到固定端口 probe 记录，确认其 `provider` 为 `deepseek_official` 且 `fallback_from_provider` 为 `rightcode`。
3. 查看 `iterations/deepseek_v4_pro_20260728_nofallback_retry2.json`，确认 `fallback_allowed=false`、实际 provider 为 `rightcode`、错误为 `LLM_NETWORK_ERROR`。
4. 查看 `iterations/deepseek_first_live_20260728_retry2.json`，确认 23 个案例全部为 `blocked`、无 `completed_case_ids`、比较准入为 `blocked`。
5. 查看最新分类工件，确认系统问题候选为 0，且未创建 Inbox 关联。

## 未解决问题和限制

- RightCode 直连仍不可用；固定端口的 200 来自 DeepSeek 官方回退，不能作为首轮准入成功。
- 任务 12.4 保持 `blocked`，任务 12.5 未开始。
- RightCode 直连恢复后，必须在禁 fallback 条件下重新执行同一冻结 23 案并保留逐案真实审计，之后才允许继续系统缺陷闭环。
- 最终独立结论：未判定。

## 系统问题定向修复：模型探测身份误判

- 问题：`issue-llm-probe-fallback-availability-misclassification`
- 修复范围：
  - `RightCodeLLMGateway.probe_model` 只探测请求的 provider/model，显式禁用 fallback。
  - 普通 `complete` 和 `stream` 的 fallback 策略保持不变。
  - `ModelAvailability` 与 `LLMModelProbeResponse` 新增 requested/actual provider/model、fallback、wire protocol 和 provider request ID 审计字段。
  - API 成功与失败消息均为中文，并明确结论针对请求的 RightCode 提供商。
- RED：
  - RightCode 连接失败、DeepSeek 官方可成功时，旧实现实际请求 `right.codes` 和 `api.deepseek.com` 并返回 `available`。
  - 成功探测状态缺少 `requested_provider` 等身份字段。
- GREEN/VERIFY：
  - RightCode 失败且官方可用：只请求 `right.codes`，返回 `unavailable`、`fallback_used=false`。
  - RightCode 真成功：返回 `available`，provider/model/wire/request ID 与真实响应一致。
  - 完整 RightCode、LLM API 和评测 provider 相关回归：65 passed。
  - Ruff：passed。
  - 固定端口真实验证：
    - `availability=unavailable`
    - `requested_provider=actual_provider=rightcode`
    - `requested_model_id=actual_model_id=deepseek-v4-pro`
    - `fallback_used=false`
    - `fallback_from_provider=null`
    - `wire_protocol=anthropic_messages`
    - `provider_request_id=null`
    - usage call ID：`llm-call-d9b029cfd532450eaaa85eef5ca10806`
    - usage error：`LLM_NETWORK_ERROR`
- 状态边界：
  - 未修改任务 12.4 的 `blocked` 状态。
  - 未修改任务 12.5。
  - 未 PATCH Inbox；关单由主 Agent执行。
