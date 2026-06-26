# Python 编码规范 | 太初 (Taichu) 项目

> 更新日期：2026-06-25
>
> 适用范围：`src/taichu/` 与 `tests/`
>
> 技术栈：Python 3.12+ / FastAPI / LangGraph / LangChain / Pydantic
>
> 架构基线：`.claude/management/PROJECT_ARCHITECTURE.md`

## 一、核心原则

- **可扩展性优先**：新增 Agent、Tool、LLM、存储或检索实现必须有明确入口。
- **单本小说上下文**：系统只有一个小说上下文，不设计 `project_id`、小说选择或跨小说隔离。
- **职责边界优先**：不得以“当前实现简单”“暂时够用”或“以后再拆”为理由混合职责。
- **领域层技术无关**：小说领域模型和规则不得依赖 FastAPI、LangGraph、LLM、MCP 或具体存储。
- **依赖抽象**：应用层依赖契约，基础设施层实现契约。
- **组合入口唯一**：对象创建与依赖组装集中在 `main.py`，不得散落在业务模块。
- **异步优先**：网络、文件、数据库、LLM 和 MCP 等 IO 使用 `async`/`await`。
- **类型安全**：公开接口必须提供完整类型注解，禁止使用无边界的 `Any`。
- **Agent 即插件**：新增 Agent = 新建目录 + 实现协议，不修改发现和注册逻辑。

## 二、标准包结构

```text
src/taichu/
├── __init__.py
├── main.py                            # 组合入口、FastAPI 创建与启动
├── config.py                          # 只读取和校验环境变量
│
├── api/                               # HTTP 与流式传输层
│   ├── deps.py
│   ├── router.py
│   ├── schemas/                       # API 请求/响应模型
│   └── routes/                        # 按资源拆分的路由
│
├── application/                       # 用例与能力编排
│   ├── capabilities.py                # Agent/Tool 共用能力上下文
│   ├── contracts/
│   │   ├── storage.py
│   │   └── retrieval.py
│   ├── services/                      # 普通业务流程
│   ├── agents/
│   │   ├── contract.py
│   │   ├── registry.py
│   │   └── {agent_name}/
│   │       ├── __init__.py
│   │       ├── graph.py
│   │       ├── nodes.py
│   │       └── prompts.py
│   └── tools/
│       ├── contract.py
│       ├── registry.py
│       └── {tool_name}.py
│
├── domain/                            # 技术无关的小说领域
│   ├── models/
│   ├── rules/
│   └── exceptions.py
│
└── infrastructure/                    # 可替换的技术实现
    ├── plugin_discovery.py
    ├── storage/
    ├── retrieval/
    ├── llm/
    ├── mcp/
    └── indexing/
```

完整目标目录和未来功能落点以 `PROJECT_ARCHITECTURE.md` 为准。不得再新增旧式顶层 `agents/`、`core/`、`models/`、`services/` 或 `tools/`。

## 三、分层职责与依赖

| 层 | 目录 | 负责 | 禁止 |
|---|---|---|---|
| 组合入口 | `main.py` | 创建实现、注入依赖、启动应用 | 业务逻辑、领域规则 |
| 配置 | `config.py` | 读取并校验 `.env` 和环境变量 | 创建 LLM、存储、Agent 等实例 |
| API | `api/` | 参数校验、协议转换、响应格式、传输错误映射 | 业务逻辑、直接读写数据 |
| 应用 | `application/` | Service、Agent、Tool 和用例编排 | 导入具体数据库、ChromaDB、具体 LLM Provider |
| 领域 | `domain/` | 人物、地点、大纲、时间线等模型与业务规则 | 依赖其他层或技术框架 |
| 基础设施 | `infrastructure/` | 存储、检索、LLM、MCP、索引和插件发现实现 | 小说业务规则 |

### 依赖方向

```text
api ───────────────→ application ───────────────→ domain
                           │
                           └────→ application/contracts

infrastructure ──实现────────────→ application/contracts

main.py ─→ api + application + infrastructure
```

强制规则：

- `api` 只能调用应用层公开用例，不直接调用基础设施实现。
- `application` 可以使用 `domain` 和应用契约，不依赖具体技术实现。
- `domain` 不得导入 `api`、`application` 或 `infrastructure`。
- `infrastructure` 可以实现应用契约，但不得反向编排应用用例。
- 插件发现负责返回候选插件；`main.py` 将候选插件交给应用注册中心。
- 不得通过全局单例绕过依赖方向。

## 四、模块与命名规范

### 文件和包

| 类型 | 规则 | 示例 |
|---|---|---|
| 包目录 | lowercase / snake_case | `application/agents/` |
| Python 模块 | snake_case | `knowledge_service.py` |
| Agent 目录 | snake_case、语义明确 | `style_transfer/` |
| Agent 图 | 固定为 `graph.py` | `agents/chat/graph.py` |
| Agent 节点 | 固定为 `nodes.py` | `agents/chat/nodes.py` |
| 提示词 | 固定为 `prompts.py` | `agents/chat/prompts.py` |
| 契约 | 优先使用 `contract.py` 或能力名 | `contracts/storage.py` |
| 具体实现 | 技术名 + `_backend` 或语义名 | `json_backend.py` |

### 类、函数和变量

| 类型 | 规则 | 示例 |
|---|---|---|
| 类、Pydantic Model | PascalCase | `AgentManifest`, `Character` |
| 契约 Protocol | PascalCase | `StorageBackend`, `RetrievalBackend` |
| 具体实现 | PascalCase + 技术语义 | `JsonStorageBackend` |
| 异常 | PascalCase + `Error` | `AgentNotFoundError` |
| 函数和方法 | snake_case，动词开头 | `register_agent()` |
| 工厂函数 | `create_` / `build_` | `create_app()`, `build_graph()` |
| 查询函数 | `get_` / `list_` / `search_` | `list_agents()` |
| FastAPI 依赖 | `get_` / `provide_` | `provide_knowledge_service()` |
| 布尔值 | `is_` / `has_` / `supports_` | `supports_streaming` |
| 常量 | UPPER_SNAKE_CASE | `DEFAULT_MODEL` |
| 私有成员 | `_` 前缀 | `_registered_agents` |

## 五、类型与模型规范

所有公开函数、方法、类属性和模块级变量必须有类型注解。

```python
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeAlias

AgentHandler: TypeAlias = Callable[[AgentInput], Awaitable[AgentOutput]]


class StorageBackend(Protocol):
    async def get(self, collection: str, key: str) -> dict[str, object] | None:
        ...
```

规则：

- 使用 Python 3.12 语法：`str | None`，不使用 `Optional[str]`。
- 使用内置泛型：`list[str]`、`dict[str, object]`。
- 跨层接口优先使用 `Protocol`、抽象基类或明确的 Pydantic Model。
- 外部不可信输入使用 Pydantic 校验。
- `Any` 只能用于第三方库确实无类型信息的边界，并在最小范围内收窄。
- API Schema 放在 `api/schemas/`，领域模型放在 `domain/models/`，不得混用。
- LangGraph State 属于 Agent 内部工作流模型，不得放入领域层。

## 六、Agent 插件规范

### 目录契约

```text
application/agents/{agent_name}/
├── __init__.py
├── graph.py                 # 导出 manifest 与 build_graph()
├── nodes.py                 # LangGraph 节点
├── prompts.py               # 提示词
└── state.py                 # 状态复杂时使用
```

### 协议归属

Agent 公共协议定义在：

```text
application/agents/contract.py
```

协议至少包含：

```python
manifest = AgentManifest(
    name="continuation",
    label="章节续写",
    description="根据正文和相关设定续写章节",
    input_schema=ContinuationInput,
    output_schema=ContinuationOutput,
    required_capabilities=frozenset({"llm", "knowledge_search"}),
    exposures=frozenset({"api", "ui", "mcp"}),
    supports_streaming=True,
)
```

规则：

- `name` 是稳定唯一标识，只能使用小写英文、数字和下划线。
- `required_capabilities` 声明运行依赖，不为每项能力增加布尔字段。
- `exposures` 声明可暴露渠道，未声明的渠道不得调用该 Agent。
- 输入、输出和流式能力必须由协议显式声明。
- Agent 通过注入的 capability 使用 LLM、检索、MCP 等能力。
- Agent 不得直接读取 `project_assets/`，不得直接实例化具体基础设施类。
- Agent 之间不得直接导入实现；共享能力下沉到 Tool、Service 或契约。

### 发现与注册

职责必须分离：

```text
infrastructure/plugin_discovery.py
    扫描包、动态导入、返回候选插件

application/agents/registry.py
    校验协议、检查重名、注册、查询

main.py
    调用 discovery，并将候选插件交给 registry
```

禁止：

- 在注册中心内扫描文件系统或执行动态导入。
- 在发现模块内维护已注册 Agent 状态。
- 捕获 `ImportError` 后静默跳过；必须记录插件名和失败原因。
- 通过修改固定列表来新增 Agent。

### 新增 Agent

1. 在 `application/agents/` 新建 `{agent_name}/`。
2. 实现输入输出 Schema、`manifest` 和 `build_graph()`。
3. 在测试中覆盖协议校验、核心节点和完整调用。
4. 不修改 `plugin_discovery.py`、注册中心或固定 API 路由。
5. 若需要独立页面，再新增对应前端路由；自动注册不等于自动生成专属 UI。

## 七、Tool 规范

Tool 是 Agent 可复用的原子能力，放在 `application/tools/`。

- Tool 公共协议定义在 `application/tools/contract.py`。
- Tool 注册、校验和查询放在 `application/tools/registry.py`。
- Tool 应小而明确，输入输出必须结构化。
- Tool 不包含 HTTP 逻辑，不直接创建基础设施实例。
- 一致性检查、检索封装、伏笔检查、字数统计等放 Tool。
- 跨多个实体并包含完整业务流程的能力应放 Service，不要伪装成 Tool。
- MCP Tool 必须先经 `infrastructure/mcp/capability_adapter.py` 适配，再注入应用层。

## 八、Service 与领域规范

### Service

`application/services/` 承载非 Agent 用例和跨组件编排，例如知识库 CRUD、大纲保存、正文管理、导入导出和索引重建。

- 一个公开方法对应一个明确用例。
- Service 通过构造参数接收契约，不在方法内创建实现。
- Service 负责事务和流程顺序，领域规则应调用 `domain/rules/`。
- API、Agent 和后台任务可以复用同一个 Service。

```python
class KnowledgeService:
    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    async def save_character(self, character: Character) -> None:
        validate_character(character)
        await self._storage.put("characters", character.id, character.model_dump())
```

### Domain

- `domain/models/` 只描述小说实体和值对象。
- `domain/rules/` 保存与框架无关的业务约束。
- 人物、地点、势力、功法和事件使用稳定 ID 关联。
- 中文名和文件名用于展示，不作为关联主键。
- 领域模型不得包含数据库路径、HTTP 状态码、LangGraph State 或 LLM Message。

## 九、存储、检索与数据规范

### 应用契约

```text
application/contracts/storage.py
application/contracts/retrieval.py
```

- 存储契约定义源数据的读取、保存、删除和查询能力。
- 检索契约定义关键词、语义或混合检索的统一输入输出。
- 契约不暴露 ChromaDB、SQLite、文件路径等实现细节。
- 新增实现不得要求调用方修改业务代码。

### 基础设施实现

```text
infrastructure/storage/
infrastructure/retrieval/
infrastructure/indexing/
```

- JSON、Markdown、SQLite 等存储实现分别放独立模块。
- 关键词、向量和混合检索分别实现统一检索契约。
- ChromaDB 与 embedding 缓存只属于基础设施层。
- 具体实现由 `main.py` 根据 settings 创建并注入。

### 数据边界

- `project_assets/` 整体代表当前唯一小说，应用接口不得要求调用方传入 `project_id` 或 `novel_id`。
- `project_assets/source/` 是唯一事实来源。
- `project_assets/generated/` 仅保存可重建的向量库、索引、缓存和临时文件。
- 删除 `generated/` 后必须能够从 `source/` 完整重建。
- 检索默认覆盖当前唯一小说；“主角”“世界观”等指代无需先解析小说归属。
- API、Agent、Tool 和领域层不得直接操作数据路径。
- 自动化测试必须使用 `tests/fixtures/project_assets/`，禁止污染真实小说数据。

## 十、配置与组合入口

### `config.py`

`config.py` 只负责读取和校验配置：

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    project_assets_dir: str = "project_assets"
    llm_provider: str = "deepseek"


settings = Settings()
```

禁止在 `config.py` 中创建 LLM、Storage、Retrieval、Agent Registry 或 MCP Client。

### `main.py`

`main.py` 是唯一组合入口：

```python
def create_app(settings: Settings) -> FastAPI:
    storage = create_storage(settings)
    retrieval = create_retrieval(settings, storage)
    agent_registry = AgentRegistry()

    candidates = discover_agents("taichu.application.agents")
    agent_registry.register_all(candidates)

    services = create_services(storage=storage, retrieval=retrieval)
    return create_fastapi_app(services=services, agent_registry=agent_registry)
```

规则：

- `settings` 可以是模块级只读对象，业务对象不得是隐式全局单例。
- 新增配置字段必须同步更新 `.env.example`。
- 敏感信息不得提供真实默认值或提交到 Git。
- 修改 `main.py`、`config.py`、`.env.example` 或 `pyproject.toml` 后必须验证 `start.bat`。

## 十一、FastAPI 规范

- 路由按资源拆分到 `api/routes/`。
- API 请求和响应模型放在 `api/schemas/`。
- 路由只执行校验、用例调用和响应转换。
- 应用异常在 API 边界统一映射为 HTTP 错误。
- 不在路由中创建 Service、Storage、LLM 或 Agent Graph。
- 所有 IO 路由使用 `async def`。
- 流式生成优先使用统一 SSE 响应封装，不在每个 Agent 路由重复实现。

```python
@router.post("/knowledge/characters", response_model=CharacterResponse)
async def save_character(
    request: CharacterRequest,
    service: KnowledgeService = Depends(provide_knowledge_service),
) -> CharacterResponse:
    character = request.to_domain()
    await service.save_character(character)
    return CharacterResponse.from_domain(character)
```

## 十二、Import、注释与代码风格

### Import

```python
# 标准库
from pathlib import Path

# 第三方
from fastapi import FastAPI

# 本地
from taichu.application.contracts.storage import StorageBackend
from taichu.domain.models.character import Character
```

- 按标准库、第三方、本地模块分组。
- 使用 `taichu.xxx` 绝对导入，禁止跨层相对导入。
- 禁止 `import *`。
- 导入路径必须体现真实依赖方向。

### Docstring 与注释

- 每个模块顶部用一句话说明单一职责。
- 公开类、函数和方法使用简洁的 Google 风格 docstring。
- 注释解释“为什么”，不复述代码。
- 禁止在代码注释中记录变更历史。

### 代码规模

- 函数保持单一职责，复杂分支应拆分。
- 不设置机械的绝对行数上限，但超过约 50 行应检查是否混合职责。
- 不为未来猜测创建空抽象；已经确定的职责边界必须从初始实现分离。

## 十三、异常与日志

- 捕获具体异常，不得静默吞掉 `Exception`。
- 转换异常时使用 `raise ... from error` 保留异常链。
- 领域异常放 `domain/exceptions.py`。
- 应用异常放对应应用模块，基础设施异常在边界转换为应用可理解的错误。
- 日志使用标准 `logging` 和 `%s` 参数化格式。
- 日志不得记录 API Key、完整提示词、小说正文或其他敏感内容。

```python
try:
    candidates = discover_agents(package_name)
except PluginDiscoveryError as error:
    logger.error("Agent discovery failed: package=%s error=%s", package_name, error)
    raise StartupError("Unable to discover agents") from error
```

## 十四、测试规范

```text
tests/
├── unit/
│   ├── application/
│   │   ├── services/
│   │   ├── agents/
│   │   └── tools/
│   ├── domain/
│   └── infrastructure/
├── integration/
│   ├── api/
│   ├── storage/
│   ├── retrieval/
│   └── mcp/
└── fixtures/
    └── project_assets/
```

- 测试命名：`test_{对象}_{场景}_{预期}`。
- 单元测试使用 fake 或 stub 契约实现，不依赖真实 LLM 和网络。
- Agent 测试至少覆盖协议校验、核心节点、能力缺失和流式行为。
- 插件测试分别覆盖发现失败与注册校验，不能只测合并后的 happy path。
- 存储实现必须通过同一套契约测试。
- 集成测试使用隔离的临时数据目录。
- 不得访问或修改真实 `project_assets/`。

## 十五、代码审查清单

- [ ] 新代码位于目标分层目录，没有新增旧式 `core/` 等路径
- [ ] API、应用、领域和基础设施职责没有混合
- [ ] `config.py` 未创建业务对象，实例由 `main.py` 组装
- [ ] 插件发现与协议注册保持分离
- [ ] Agent 使用 `required_capabilities` 和 `exposures`
- [ ] 新增 Agent 未修改发现、注册或固定路由逻辑
- [ ] API Schema、领域模型和 LangGraph State 没有混用
- [ ] 应用层依赖契约，不依赖具体存储、检索或 LLM Provider
- [ ] 源数据与可重建数据严格分离
- [ ] 未引入 `project_id`、小说选择器或跨小说过滤等多小说设计
- [ ] 领域关联使用稳定 ID，不依赖中文名或文件名
- [ ] 公开接口有类型注解和必要 docstring
- [ ] IO 使用异步接口，没有阻塞事件循环
- [ ] 异常处理保留上下文，日志不泄露敏感内容
- [ ] 测试不访问真实小说资产
- [ ] 配置或启动相关变更已验证 `start.bat`

---

**维护者**：Taichu Team
