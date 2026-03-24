# WriteAgent — 多智能体 AI 小说写作系统

WriteAgent 是一个基于 **LangGraph + Qwen-max + ChromaDB** 构建的多智能体协作写作框架，通过多个专职 Agent 的分工协作，逐场景生成具有内部一致性的长篇小说。系统配备 FastAPI 后端、Gradio 前端以及完整的审计日志体系。

---

## 目录

- [系统架构](#系统架构)
- [Agent 工作流程](#agent-工作流程)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [快速上手](#快速上手)
- [配置说明](#配置说明)
- [API 参考](#api-参考)
- [已知问题与注意事项](#已知问题与注意事项)
- [测试](#测试)

---

## 系统架构

```
用户 (Gradio UI / REST API / WebSocket)
           │
           ▼
    FastAPI 后端 (port 8000)
           │
           ▼
  LangGraph StateGraph（novel_graph）
           │
    ┌──────┴──────────────────────────────────────────┐
    │                                                  │
    ▼                                                  │
worldbuilding → character → plot → consistency        │
                                        │             │
                              ┌─────────┴──────┐      │
                              │                │      │
                           narrative    negotiation   │
                              │                │      │
                              ▼         human_review  │
                             END               └──────┘
           │
           ▼
  ChromaDB（向量持久化存储）
  ├── world_entities   （人物/地点/势力/法器）
  ├── world_rules      （世界规则）
  └── scene_archive    （已完成场景摘要归档）
```

---

## Agent 工作流程

每个场景依次经过以下阶段，状态通过 `GraphState` TypedDict 在节点间共享：

| 阶段 | Agent | 职责 |
|------|-------|------|
| `worldbuilding` | WorldbuildingAgent | 读取世界规则，为本场景生成世界背景上下文；若草稿违反绝对规则则发起 **Veto（否决）** 并输出修正稿 |
| `character` | CharacterAgent | 从 ChromaDB 检索角色状态，更新角色记忆，返回各角色当前状态摘要 |
| `plot` | PlotAgent | 基于世界上下文、角色状态和人类注入事件生成场景草稿 |
| `consistency` | ConsistencyChecker | 对草稿与实体库做矛盾检测；无矛盾 → 直接进入 narrative，有矛盾 → 进入 negotiation |
| `negotiation` | 协商子图 | PlotAgent 修订草稿 → WorldbuildingAgent 验证 → ConsistencyChecker 复检，最多循环 `MAX_NEGOTIATION_ROUNDS` 次；未解决则升级到 `human_review` |
| `human_review` | 暂停点 | 等待人类通过 `/inject` 接口注入修正事件，再重新触发一致性检查 |
| `narrative` | NarrativeOutputAgent | 将草稿润色为最终正式散文，归档场景摘要到 ChromaDB |

---

## 项目结构

```
WriteAgent/
├── main.py                     # 入口，uvicorn 启动 FastAPI
├── requirements.txt
├── .env.example                # 环境变量模板
│
├── config/
│   ├── settings.py             # Pydantic-settings 配置（读取 .env）
│   └── constants.py            # 全局常量（实体类型、规则类型、WS 事件等）
│
├── graph/
│   ├── state.py                # GraphState TypedDict + initial_state()
│   ├── graph_builder.py        # 构建并编译 LangGraph StateGraph
│   ├── nodes.py                # 各节点函数（Agent 的薄包装）
│   ├── edges.py                # 条件路由函数
│   └── negotiation_subgraph.py # 协商循环子图（同步）
│
├── agents/
│   ├── base_agent.py           # 抽象基类：LLM 调用、JSON 解析、审计日志
│   ├── worldbuilding_agent.py
│   ├── character_agent.py
│   ├── plot_agent.py
│   ├── consistency_checker.py
│   └── narrative_output_agent.py
│
├── memory/
│   ├── chroma_client.py        # ChromaDB 客户端单例 + Collection 初始化
│   ├── schemas.py              # Pydantic 数据模型（EntityDoc, WorldRuleDoc, SceneArchiveDoc）
│   ├── entity_store.py         # ChromaDB CRUD 操作
│   └── retrieval.py            # 三层上下文构建（热/温/冷）
│
├── prompts/
│   ├── registry.py             # 版本化 Prompt 注册表（YAML 加载 + 缓存）
│   └── v1/                     # v1 版本各 Agent 的 system + user_template
│       ├── worldbuilding.yaml
│       ├── character.yaml
│       ├── plot.yaml
│       ├── consistency_checker.yaml
│       └── narrative_output.yaml
│
├── api/
│   ├── app.py                  # FastAPI 工厂函数 + CORS + 路由注册
│   ├── dependencies.py         # 依赖注入（内存状态存储、WS 队列）
│   ├── models.py               # 请求/响应 Pydantic 模型
│   ├── websocket.py            # WebSocket 流式事件推送
│   └── routes/
│       ├── novel.py            # 小说生命周期（start / next_scene / inject / status / output）
│       ├── entities.py         # 实体 CRUD + 知识图谱
│       ├── audit.py            # 审计日志查询
│       └── admin.py            # Prompt 版本管理 + 健康检查
│
├── guardrails/
│   ├── input_sanitizer.py      # 提示词注入检测 + HTML 清洗
│   └── content_filter.py       # 输出内容安全过滤（规则匹配）
│
├── utils/
│   ├── llm_client.py           # OpenAI 兼容客户端（指向 DashScope）
│   ├── audit_logger.py         # JSONL 审计日志（内存 deque + 磁盘）
│   └── token_counter.py        # tiktoken cl100k_base token 估算
│
├── ui/
│   ├── app.py                  # Gradio 多标签页 UI 入口（port 7860）
│   └── tabs/
│       ├── writer_tab.py       # 写作主界面（启动/生成场景/注入事件）
│       ├── world_graph_tab.py  # 实体知识图谱可视化
│       ├── conflict_panel_tab.py # 协商冲突面板
│       └── audit_tab.py        # 审计日志查看
│
└── tests/
    ├── unit/                   # 单元测试（mock LLM 调用）
    └── integration/            # 集成测试（httpx TestClient）
```

---

## 环境要求

- Python 3.11+
- [DashScope API Key](https://dashscope.aliyuncs.com/)（Qwen-max 通道）
- （可选）[LangSmith API Key](https://smith.langchain.com/)（链路追踪）

---

## 快速上手

### 1. 克隆并安装依赖

```bash
git clone <repo-url>
cd WriteAgent

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

打开 `.env`，至少填写：

```env
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxx   # 必填
QWEN_MODEL_NAME=qwen-max            # 默认即可
LANGCHAIN_TRACING_V2=false          # 没有 LangSmith Key 时务必设为 false（见已知问题）
```

### 3. 启动后端

```bash
# 方式一：直接运行
python main.py

# 方式二：uvicorn（推荐开发）
uvicorn main:app --reload --port 8000
```

启动后访问 `http://localhost:8000/docs` 查看交互式 API 文档。

健康检查：

```bash
curl http://localhost:8000/api/v1/admin/health
```

### 4. 启动前端（可选，另开终端）

```bash
python -m ui.app
```

访问 `http://localhost:7860`，包含四个标签页：

- **Writer** — 启动小说、逐场景生成、人类注入事件
- **World Graph** — 实体知识图谱可视化
- **Conflict Panel** — 查看协商过程与矛盾记录
- **Audit** — 逐 Agent 调用的完整审计日志

### 5. 快速 API 示例

#### 启动一部小说

```bash
curl -X POST http://localhost:8000/api/v1/novel/start \
  -H "Content-Type: application/json" \
  -d '{
    "genre": "Fantasy",
    "style_guide": "Third-person limited, literary fiction",
    "first_scene_brief": "Elena discovers an ancient map in her grandmother attic",
    "initial_characters": [
      {"name": "Elena", "description": "A curious young archivist with black hair"},
      {"name": "Marcus", "description": "A gruff but loyal blacksmith"}
    ],
    "initial_world_rules": [
      {"description": "Magic requires rare crystals", "severity": "absolute", "category": "magic"},
      {"description": "No firearms exist in this world", "severity": "absolute", "category": "physics"}
    ]
  }'
# 返回 novel_id，保存备用
```

#### 生成下一场景

```bash
NOVEL_ID="<上一步返回的 novel_id>"

curl -X POST http://localhost:8000/api/v1/novel/$NOVEL_ID/scene/next \
  -H "Content-Type: application/json" \
  -d '{"scene_brief": "Elena follows the map into the Silvermere Forest"}'
```

#### 注入人类事件（Human-in-the-Loop）

```bash
curl -X POST http://localhost:8000/api/v1/novel/$NOVEL_ID/inject \
  -H "Content-Type: application/json" \
  -d '{"event": "A mysterious stranger hands Elena a sealed letter", "next_scene_brief": "Elena opens the letter"}'
```

#### WebSocket 实时监听

```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/${novelId}/stream`);
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // event_type: prose_chunk | phase_change | negotiation | veto | human_required | error | done
  console.log(data);
};
```

---

## 配置说明

所有配置通过 `.env` 文件或环境变量注入，由 `config/settings.py` 统一管理：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DASHSCOPE_API_KEY` | `""` | **必填**，DashScope API Key |
| `QWEN_MODEL_NAME` | `qwen-max` | 使用的模型名称 |
| `QWEN_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | DashScope OpenAI 兼容端点 |
| `LLM_TEMPERATURE` | `0.8` | 生成温度 |
| `LLM_MAX_TOKENS` | `2048` | 单次生成最大 token 数 |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB 持久化目录 |
| `SLIDING_WINDOW_SIZE` | `5` | 热上下文窗口（保留最近 N 场景原文） |
| `HOT_CONTEXT_MAX_TOKENS` | `8000` | 热上下文 token 预算 |
| `RETRIEVAL_K` | `8` | ChromaDB 向量检索 top-k |
| `MAX_NEGOTIATION_ROUNDS` | `3` | 协商最大轮数，超出则升级到人类审核 |
| `LANGCHAIN_TRACING_V2` | `true` | LangSmith 追踪开关（**无 Key 时务必设为 false**） |
| `LANGCHAIN_API_KEY` | `""` | LangSmith API Key |
| `PROMPT_VERSION` | `v1` | 当前激活的 Prompt 版本 |
| `PROMPTS_DIR` | `./prompts` | Prompt YAML 文件根目录 |

### Prompt 版本管理

通过 `prompts/{version}/{agent_name}.yaml` 管理多版本 Prompt，每个 YAML 包含：

```yaml
system: |
  <系统 Prompt>
user_template: |
  <用户 Prompt 模板，使用 {variable} 占位符>
```

运行时热切换版本：

```bash
curl -X PUT http://localhost:8000/api/v1/admin/prompts/plot_agent/v2
```

---

## 已知问题与注意事项

### 🐛 Bug 1：`entities.py` 路由顺序导致 `/graph` 端点不可达

**文件**：`api/routes/entities.py`，第 52-71 行

`GET /{novel_id}/graph` 路由定义在 `GET /{novel_id}/{entity_id}` **之后**。FastAPI 按注册顺序匹配路由，请求 `/entities/{novel_id}/graph` 会被前一个路由以 `entity_id="graph"` 拦截，导致知识图谱端点永远无法命中。

**修复方法**：将 `get_entity_graph` 路由的 `@router.get("/{novel_id}/graph", ...)` 装饰器和函数体移至 `get_single_entity` 路由定义**之前**。

---

### 🐛 Bug 2：`plot_agent.py` subplot 事件覆盖普通 plot_events

**文件**：`agents/plot_agent.py`，第 56-69 行

当 LLM 返回 `new_subplot` 时，代码执行 `update["plot_events"] = [f"[SUBPLOT] {new_subplot}"]`，这会**覆盖**同一 `update` 字典里已经赋值的 `new_events`，导致当轮所有普通情节事件丢失，只保留子情节。

**修复方法**：改为追加而非覆盖，即 `update["plot_events"] = new_events + [f"[SUBPLOT] {new_subplot}"]`。

---

### ⚠️ 注意 1：LangSmith 追踪默认开启，空 Key 会引发错误

`settings.py` 中 `langchain_tracing_v2` 默认为 `True`，但 `langchain_api_key` 默认为空字符串。在没有有效 Key 的情况下启用追踪会导致 LangChain 内部网络请求失败，可能产生难以排查的异常。

**建议**：在 `.env` 中明确设置 `LANGCHAIN_TRACING_V2=false`，仅在需要追踪时启用。

---

### ⚠️ 注意 2：`negotiation_subgraph.py` 重复实例化 Agent

`WorldbuildingAgent` 和 `ConsistencyChecker` 在 `graph/nodes.py` 中已作为模块级单例创建，但 `graph/negotiation_subgraph.py` 中又分别实例化了一次（`_worldbuilding = WorldbuildingAgent()`，`_checker = ConsistencyChecker()`），形成冗余的第三组实例。目前无功能性影响，但会造成重复内存占用。

---

### ⚠️ 注意 3：Token 计数使用 GPT-4 分词器（cl100k_base）

`utils/token_counter.py` 使用 tiktoken 的 `cl100k_base`（GPT-4 分词器）估算 Qwen-max 的 token 消耗。对于中文或混合文本，两者分词粒度差异较大，实际 token 数可能被低估，影响 `HOT_CONTEXT_MAX_TOKENS` 等上下文预算控制的精度。

---

### ⚠️ 注意 4：Novel 状态仅保存在内存，重启后丢失

`api/dependencies.py` 中的 `_novel_states` 字典是进程内存储。FastAPI 服务重启后，所有正在进行的小说状态将全部丢失。代码注释中已提示"生产环境请替换为 Redis"。

---

### ⚠️ 注意 5：WebSocket 使用轮询推送（0.5s 延迟）

`api/websocket.py` 的 `ws_stream` 每 500ms 轮询一次事件队列，而非事件触发式推送。对实时性要求较高的场景会有最多 500ms 的推送延迟，且在空闲期持续占用 CPU。

---

### ℹ️ 说明：审计日志路径为相对路径

`utils/audit_logger.py` 将 JSONL 审计日志写入相对路径 `audit_logs/`，具体位置取决于进程启动时的工作目录（通常是项目根目录）。部署时建议将其改为绝对路径或通过环境变量配置。

---

## 测试

```bash
# 安装测试依赖（已含于 requirements.txt）
pip install pytest pytest-asyncio httpx

# 运行全部测试
pytest tests/ -v

# 只跑单元测试（不需要启动服务）
pytest tests/unit/ -v

# 只跑集成测试（需要服务运行或使用 TestClient）
pytest tests/integration/ -v
```

单元测试通过 `unittest.mock.patch` 隔离 LLM 调用，不需要真实 API Key；集成测试使用 FastAPI 的 `TestClient` 或 httpx，也不依赖外部服务。

---

## 三层上下文记忆策略

系统通过 `memory/retrieval.py` 的 `build_context_for_agent()` 实现分层上下文管理，在 token 预算内最大化相关信息密度：

- **热层（Hot）**：最近 `SLIDING_WINDOW_SIZE` 个场景的完整原文，保证短程叙事连贯
- **温层（Warm）**：从 ChromaDB 向量检索 top-k 语义相关实体（人物/地点/势力等），覆盖长程引用
- **冷层（Cold）**：所有 `absolute`（绝对）世界规则，始终置于上下文末尾，确保硬性约束不被遗忘

---

## 内容安全机制

- **输入层**：`guardrails/input_sanitizer.py` 检测提示词注入（`ignore previous instructions` 等模式），超长截断，HTML 标签清洗
- **输出层**：`guardrails/content_filter.py` 基于正则规则过滤危害性内容，支持 `G / PG-13 / R / UNRATED` 分级

---

## 扩展指南

### 添加新 Agent

1. 在 `agents/` 下创建继承 `BaseAgent` 的新类，实现 `run(state) -> dict`
2. 在 `prompts/v1/` 下添加对应的 YAML Prompt 文件
3. 在 `graph/nodes.py` 中添加节点函数
4. 在 `graph/graph_builder.py` 中注册节点和边

### 添加新 Prompt 版本

在 `prompts/v2/` 下创建同名 YAML 文件，然后通过 API 或 `.env` 切换：

```bash
curl -X PUT http://localhost:8000/api/v1/admin/prompts/plot_agent/v2
```

### 替换 LLM 后端

修改 `utils/llm_client.py`，将 `base_url` 指向任何 OpenAI 兼容端点，并更新 `QWEN_MODEL_NAME` 为对应模型名称即可。
