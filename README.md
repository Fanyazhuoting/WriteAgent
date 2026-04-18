# WriteAgent — 多智能体 AI 小说写作系统

WriteAgent 是一个基于 **LangGraph + Qwen-max + ChromaDB** 构建的多智能体协作写作框架，通过多个专职 Agent 的分工协作，逐场景生成具有内部一致性的长篇小说。系统配备 FastAPI 后端、静态 Web 前端以及完整的审计日志体系。

---

## 目录

- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [Agent 工具箱 (MCP)](#agent-工具箱-mcp)
- [Agent 工作流程](#agent-工作流程)
- [一致性检测机制](#一致性检测机制)
- [实体记忆模型](#实体记忆模型)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [快速上手](#快速上手)
- [配置说明](#配置说明)
- [API 参考](#api-参考)
- [测试](#测试)

---

## 核心特性

- **多智能体协作流**：基于 LangGraph 构建，由 Worldbuilding, Plot, Character, Consistency, Narrative 等多个专业 Agent 协作完成创作。
- **MCP 增强工具集**：引入 Model Context Protocol (MCP) 架构，赋予 Agent 主动调用外部工具（如时钟、地理计算、安全过滤）的能力。
- **五层记忆体系**：
    1. **工作记忆** (GraphState)：当前场景的中间推理与草稿。
    2. **短时记忆** (Prose History)：最近场景的滑动窗口上下文，保证叙事连贯。
    3. **长时记忆** (Entity Store)：基于 ChromaDB 的结构化事实记忆（人设、等级等）。
    4. **情节存档** (Scene Archive)：全书剧情摘要的 RAG 检索，支持长线伏笔。
    5. **审计记忆** (Audit Logs)：全链条透明的 JSON 调用记录，记录 AI 决策过程。
- **硬核逻辑校验**：
    - **物理时空追踪**：强制性的世界时钟管理与地理坐标校验，杜绝“时间混乱”与“角色瞬移”。
    - **混合一致性检查**：正则预扫描 + LLM 语义碰撞，确保核心属性（发色、生死等）永不矛盾。
- **负责任的 AI (RAI) 实践**：
    - **安全卫士 (Guardrails)**：集成安全 MCP，主动拦截注入攻击、隐私泄露及不合规内容。
    - **可解释性 (XAI)**：前端实时展示 Agent 的推理决策链路 (Reasoning Chain) 与完整审计日志。

---

## 系统架构

```
用户 (Static Web UI / REST API / WebSocket)
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
  ├── world_entities   （人物/地点/势力/法器/系统）
  ├── world_rules      （世界规则）
  └── scene_archive    （已完成场景摘要归档）
```

---

## Agent 工具箱 (MCP Tools)

系统通过统一的 **MCP (Model Context Protocol)** 架构管理 Agent 可调用的工具，支持多轮工具往返与自动重试机制：

### 1. 安全防御 (Security MCP)
- `detect_and_sanitize_injection`: [输入层] 拦截提示词注入攻击。
- `verify_content_safety`: [输出层] 内容合规性自我审计（支持 G/PG-13/R 分级）。
- `scan_pii_exposure`: [隐私层] 扫描并防止敏感隐私信息泄露。

### 2. 物理逻辑 (Logic MCP)
- `check_world_clock`: [强制] 获取当前世界时间线。
- `advance_world_clock`: [强制] 自动推进小说内部时间。
- `sync_world_clock`: 处理剧情大跨度跳跃（如“七天后”）。
- `validate_travel_feasibility`: 基于坐标 (x, y) 进行地理距离与旅行时间演算。

---

## Agent 工作流程

每个场景依次经过以下阶段，状态通过 `GraphState` TypedDict 在节点间共享：

| 阶段 | Agent | 职责 | 工具接入 |
|------|-------|------|------|
| `worldbuilding` | WorldbuildingAgent | 读取世界规则，为本场景生成世界背景上下文 | Security MCP |
| `character` | CharacterAgent | 从 ChromaDB 检索角色档案；返回各角色状态 | - |
| `plot` | PlotAgent | 基于上下文生成场景草稿；**必须维护世界时间线** | Logic MCP |
| `consistency` | ConsistencyChecker | 对草稿与实体库做双层矛盾检测 | - |
| `negotiation` | 协商子图 | 修订 Agent 携带实体永久属性上下文修订草稿 | - |
| `narrative` | NarrativeOutputAgent | 润色为最终散文；写回状态；执行安全自审 | Security MCP |

---

## 一致性检测机制

ConsistencyChecker 采用**代码预检 + LLM 判断**的两阶段策略，避免对 LLM 过度依赖。

#### 阶段 1 — 代码预检（`_pre_check_physical_attributes`）

在调用 LLM 前，基于 `core_attributes` 中存储的结构化颜色值，对发色、眼色、肤色做确定性扫描：

- 使用**所有格近邻检测**（`_find_attributed_value`）：仅当角色名出现在颜色词左侧 30 字符以内时才认定归属（匹配"林月的银色发丝"这类所有格结构），消除跨角色误判
- 仅在 draft 明确写出不同颜色值时产生 hint，中性描述或缺席不产生 hint

#### 阶段 2 — LLM 判断

LLM 收到预检 hints 及结构化实体快照（`CORE ATTRIBUTES` + `EXTENDED ATTRIBUTES` + `PERMANENT DESCRIPTION`）后执行三项任务：

1. **核实预检 hints**：逐条确认或否定代码预检的发现
2. **扩展属性矛盾检查**：逐一比对实体的 `EXTENDED ATTRIBUTES`（灵根、修炼路线、超能力类型等永久事实）与 draft，仅在 draft **明确写出**冲突的类型/类别名称时 flag；颜色、外形、通用动作词不构成证据
3. **世界规则与剧情连续性检查**：
   - 世界规则（全等级）：draft 明确违反即 flag；规则严重程度决定矛盾严重程度（absolute/hard → critical，soft → minor）
   - 规则与属性交叉检测：若规则声明某属性不可变，且 draft 明确使用了不同的具名值，则合并报告为 critical
   - 不可逆后果绕过（死亡/永久残疾等被撤销）、已摧毁事物被当作完好使用
   - 真正不确定的情况不 flag，宁漏勿误

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
├── agents/
│   ├── base_agent.py           # 支持 MCP 多轮调用与 novel_id 自动修正
│   └── ...
├── guardrails/
│   ├── security_mcp.py         # 安全工具注册中心
│   ├── logic_mcp.py            # 逻辑工具注册中心
│   └── ...
├── memory/
│   ├── spatio_temporal.py      # 时间推进与地理演算逻辑
│   └── ...
├── utils/
│   ├── mcp_types.py            # MCP 协议核心定义 (MCPTool, MCPRegistry)
│   ├── audit_logger.py         # 增强版 JSONL 审计（支持全量 Prompt 记录）
│   └── ...
└── ...
```

---

## 环境要求

- Python 3.11+
- [DashScope API Key](https://dashscope.aliyuncs.com/)（Qwen-max 通道）

---

## 快速上手

### 1. 克隆并安装依赖

```bash
git clone <repo-url>
cd WriteAgent

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python --version                   # 需为 Python 3.11+
pip install -r requirements.txt
```

说明：当前仓库前端使用 `ui/static` 下的静态页面，不依赖 Gradio。

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

## ML/LLMSecOps Pipeline

仓库已补充一套面向本项目的 ML/LLMSecOps 设计与骨架文件：

- [LLMSecOps Pipeline](./docs/llmsecops-pipeline.md)
- [GitHub Actions CI](./.github/workflows/ci.yml)
- [Docker Release Workflow](./.github/workflows/docker-release.yml)
- [Deploy Staging Workflow](./.github/workflows/deploy-staging.yml)
- [Deploy Production Workflow](./.github/workflows/deploy-production.yml)
- [Dockerfile](./Dockerfile)
- [Docker Compose](./docker-compose.yml)
- [Prometheus Alerts Template](./ops/monitoring/prometheus-alerts.yml)

### Docker 本地运行

```bash
cp .env.example .env
docker compose up --build
```

默认访问：

```text
http://localhost:8000
```

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
