# WriteAgent — 多智能体 AI 小说写作系统

WriteAgent 是一个基于 **LangGraph + Qwen-max + ChromaDB** 构建的多智能体协作写作框架，通过多个专职 Agent 的分工协作，逐场景生成具有内部一致性的长篇小说。系统配备 FastAPI 后端、Gradio 前端以及完整的审计日志体系。

---

## 目录

- [系统架构](#系统架构)
- [Agent 工作流程](#agent-工作流程)
- [一致性检测机制](#一致性检测机制)
- [实体记忆模型](#实体记忆模型)
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
用户 (Gradio UI / Static Web UI / REST API / WebSocket)
           │
           ▼
    FastAPI 后端 (port 8000)
           │
           ▼
  LangGraph StateGraph（novel_graph）
           │
    ┌──────┴──────────────────────────┐
    │                                  │
    ▼                                  │
worldbuilding → character → plot → consistency
                                        │
                              ┌─────────┴──────────┐
                              │                    │
                           narrative          negotiation
                              │                    │
                             END          (最多 MAX_NEGOTIATION_ROUNDS 轮)
                                                   │
                                               narrative
                                                   │
                                                  END
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
| `worldbuilding` | WorldbuildingAgent | 读取世界规则，为本场景生成世界背景上下文 |
| `character` | CharacterAgent | 从 ChromaDB 检索角色档案；返回各角色当前动态状态摘要（`character_states`）及永久属性快照（`character_profiles_snapshot`、`new_character_permanent`）；本阶段不写入 DB |
| `plot` | PlotAgent | 基于世界上下文、角色状态和人类注入事件，严格按场景提要生成场景草稿 |
| `consistency` | ConsistencyChecker | 对草稿与实体库做双层矛盾检测（见[一致性检测机制](#一致性检测机制)）；无矛盾 → 直接进入 narrative，有矛盾 → 进入 negotiation |
| `negotiation` | 协商子图 | 修订 Agent 携带实体永久属性上下文修订草稿 → ConsistencyChecker 复检，最多循环 `MAX_NEGOTIATION_ROUNDS` 次；无论是否解决均继续进入 narrative，未解决的矛盾保留在 `negotiation_log` 中供审计 |
| `narrative` | NarrativeOutputAgent | 将草稿润色为最终散文；**统一将本场景角色状态写回 ChromaDB**（永久属性不变，仅更新 `current_state`）；归档场景摘要；若发现 draft 与 scene_history 存在事实差异，**可对齐至已建立事实**，但每次修正必须写入 `corrections_log`（不允许静默修正） |

---

## 一致性检测机制

ConsistencyChecker 采用**代码预检 + LLM 判断**的两阶段策略，避免对 LLM 过度依赖。

### 阶段 1 — 代码预检（`_pre_check_physical_attributes`）

在调用 LLM 前，用正则对体貌特征（发色、眼色）做确定性扫描：

- 从实体 PERMANENT 中提取已知颜色值（支持中英文）
- 检查 draft 中该角色名附近是否出现**不同的**颜色词
- 仅在 draft 明确写出不同值时产生 hint，缺席或中性描述不产生 hint

示例：
- ✓ 产生 hint：PERMANENT="金色头发" → draft 写"紫色头发" — 明确不同值
- ✗ 不产生 hint：draft 写"她的发丝飘扬" — 中性描述
- ✗ 不产生 hint：draft 未提及头发 — 缺席 ≠ 矛盾

### 阶段 2 — LLM 判断

LLM 收到预检 hints 后执行两项任务：

1. **核实 hints**：逐条确认或否定代码预检的发现（LLM 角色是"核实"而非"发现"，更可靠）
2. **世界规则与剧情连续性检查**：
   - 世界规则（全等级）：draft 明确违反即 flag；规则严重程度决定矛盾严重程度（absolute/hard → critical，soft → minor）
   - 不可逆后果绕过：死亡/永久残疾等被撤销
   - 已建立的物理不可能性：已被明确摧毁的事物被当作完好使用
   - 真正不确定的情况不 flag

**双重兜底**：若 LLM 漏判了代码已发现的 hint，代码会自动将其补充进 `contradictions`，带 `"source": "pre_scan"` 标记供人工审阅。

---

## 实体记忆模型

`EntityDoc` 将角色信息分为两个独立字段，解决动态状态污染永久属性的问题：

| 字段 | 含义 | 存储方式 | 何时写入 |
|---|---|---|---|
| `description` | **永久属性**：外貌、物种、背景等不变事实 | 作为 ChromaDB document 进行语义嵌入 | 角色首次出现时写入，此后**永不覆盖** |
| `current_state` | **动态状态**：位置、情绪、目标等场景相关状态 | 存储在 ChromaDB metadata | 每场景 narrative 阶段结束后更新 |

新角色首次出现时，CharacterAgent 通过 `new_character_permanent` 字段单独传递永久属性，NarrativeOutputAgent 据此建立 DB 条目，确保永久属性不被动态状态污染。若 CharacterAgent 未提供该字段（LLM 不合规），NarrativeOutputAgent 会自动发起一次小型专项 LLM 调用来提取永久属性，并在 audit log 中记录此次兜底行为。

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
│       ├── audit.py            # 审计日志查询（含 /conflicts、/negotiations 端点）
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
│   ├── static/
│   │   ├── index.html          # 静态 Web UI（由 FastAPI 在 port 8000/static 提供）
│   │   └── app.js              # 前端逻辑
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

### 3. 启动项目

```bash
uvicorn main:app --reload --port 8000
```

访问 `http://localhost:8000`，包含四个标签页：

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
      {"name": "Elena", "description": "A curious young archivist with black hair and green eyes"},
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

#### 注入人类事件

```bash
curl -X POST http://localhost:8000/api/v1/novel/$NOVEL_ID/inject \
  -H "Content-Type: application/json" \
  -d '{"event": "A mysterious stranger hands Elena a sealed letter", "next_scene_brief": "Elena opens the letter"}'
```

#### 查询冲突记录

```bash
# 查看当前小说所有冲突（可按场景号过滤）
curl "http://localhost:8000/api/v1/audit/$NOVEL_ID/conflicts?scene_number=3"
```

#### WebSocket 实时监听

```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/${novelId}/stream`);
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // event_type: prose_chunk | phase_change | negotiation | error | done
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
| `MAX_NEGOTIATION_ROUNDS` | `3` | 协商最大轮数；超出后直接进入 narrative，未解决矛盾保留在审计日志中 |
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
