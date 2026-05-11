# LamImager 架构

## 系统概述

LamImager 是一个单体 Web 应用，用于管理 AI 图像生成任务，采用对话式 UI。它结合了 FastAPI 后端 (Python 3.14+) 和 Vue3 前端，使用 SQLite 进行数据持久化。

```
┌─────────────────────────────────────────────────────────────┐
│                        浏览器                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 Vue3 SPA (Vite)                      │   │
│  │  Pinia Stores ← API 客户端 (Axios)                   │   │
│  │  Sessions.vue (主界面，带助手侧边栏)                  │   │
│  └──────────────────────┬──────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │ HTTP/REST
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI 后端                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Routers   │→ │  Services   │→ │   Models    │        │
│  │ (11 个模块) │  │ (15 个服务) │  │ (9 张表)    │        │
│  └─────────────┘  └─────────────┘  └──────┬──────┘        │
│                                           │                │
│  ┌────────────────────────────────────────┼──────────────┐ │
│  │              外部 APIs                  │              │ │
│  │  LLM Client ──────► 兼容 OpenAI 的 LLM API            │ │
│  │  Image Client ────► 兼容 OpenAI 的图像 API            │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     SQLite 数据库                            │
│  data/lamimager.db (AES-256-GCM 加密的 API 密钥)           │
└─────────────────────────────────────────────────────────────┘
```

## 核心组件

### 后端 (FastAPI)

| 组件 | 用途 | 文件 |
|------|------|------|
| Routers | HTTP 端点定义 | `app/routers/*.py` |
| Services | 业务逻辑，外部 API 调用 | `app/services/*.py` (15: agent_bridge, agent_intent, agent_service, api_manager, billing, generate, plan_executor, plan_template, prompt_optimizer, reference, rule_engine, session_manager, settings, skill_engine, task_manager) |
| Models | SQLAlchemy ORM 定义 | `app/models/*.py` |
| Schemas | Pydantic 验证/序列化 | `app/schemas/*.py` |
| Utils | 加密，LLM 客户端，图像客户端 | `app/utils/*.py` |
| Middleware | 图片代理 SSRF 防护 | `app/middleware/` |

### 前端 (Vue3)

| 组件 | 用途 | 文件 |
|------|------|------|
| Views | 页面组件 | `src/views/*.vue` |
| API 客户端 | Axios HTTP 客户端 | `src/api/*.ts` (12 个模块，含 sse.ts) |
| Stores | Pinia 状态管理 | `src/stores/*.ts` |
| Composables | 可复用组合式函数 | `src/composables/*.ts` (useSessionEvents, useDialog, useMarkdown, useDownload) |
| Components | 共享 UI 组件 | `src/components/` (AgentStreamCard, CheckpointOverlay, ErrorBoundary, ConfirmDialog) |
| Types | TypeScript 接口 | `src/types/index.ts` |

## 数据模型

| 模型 | 用途 |
|------|------|
| `api_providers` | API 配置 (LLM + 图像生成 + 联网搜索)，加密密钥 |
| `skills` | 可复用的提示词模板 |
| `rules` | 全局配置规则 (default_params/filter/workflow) |
| `billing_records` | 每次 API 调用的费用追踪 (关联到会话) |
| `reference_images` | 参考图片元数据，包含强度/裁剪配置 |
| `sessions` | 聊天式 UI 的会话 |
| `messages` | 会话内的消息 (user/assistant/system/agent) |
| `app_settings` | 应用设置 (默认提供商，图片尺寸，max_concurrent，search_retry_count，download_directory，agent_checkpoint_rules) |
| `plan_templates` | 规划模板，含变量用于模板化规划 |

## 数据流

### 基于会话的生成流程

```
用户输入 (可选附件 + 参考图片)
    │
    ▼
┌──────────────────┐
│ Sessions.vue     │  带文件上传的聊天输入 (base64)
│                  │  contextImageList 图片条带编号徽章
│                  │  发送 context_messages (可用 image_urls)
└────────┬─────────┘
         │ POST /api/sessions/{id}/generate
         │  { prompt, reference_images, reference_labels, context_messages }
         ▼
┌──────────────────┐
│ session.py router│  验证输入，创建消息
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ generate_service │  应用技能/规则，构建多模态上下文
│                  │  reference_labels 提供 [图N] 编号映射
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ ImageClient      │  图生图三级降级:
│                  │  ① chat_edit() → /v1/chat/completions (多模态，编号标签)
│                  │  ② edit()      → /v1/images/edits (原生)
│                  │  ③ Vision LLM  → /v1/images/generations (文字兜底)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ 创建账单记录     │  自动记录费用
└──────────────────┘
```

### LLM 助手流程 (流式)

```
用户消息 (可选附件)
    │
    ▼
┌──────────────────┐
│ Sessions.vue     │  助手侧边栏对话 / 优化 / 规划
└────────┬─────────┘
         │ POST /api/prompt/stream (SSE)
         ▼
┌──────────────────┐
│ stream_llm_chat  │  调用 LLM API (流式)
└────────┬─────────┘
         │ 逐 token (SSE)
         ▼
┌──────────────────┐
│ 前端渲染         │  实时流式显示
└────────┬─────────┘
         │ [DONE] 事件
         ▼
┌──────────────────┐
│ 创建账单记录     │  记录 token 使用量
└──────────────────┘
```

## 安全

### API 密钥加密

- 算法: AES-256-GCM
- 密钥派生: SHA-256(MAC 地址 + 主机名)
- 存储: Base64(nonce + ciphertext + tag) 在 SQLite 中
- 响应脱敏: 只显示最后 4 个字符
- 解密异常处理: 捕获并记录日志，不会导致请求崩溃

### 加密流程

```python
# 加密
key = derive_key()  # 从机器指纹派生
nonce = os.urandom(12)
ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
stored = base64.b64encode(nonce + ciphertext)

# 解密
combined = base64.b64decode(stored)
nonce, ciphertext = combined[:12], combined[12:]
plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
```

### SSRF 防护 (图片代理)

`/api/images/proxy` 端点实现了服务端 URL 获取的安全控制:

1. **协议限制**: 仅允许 `http` 和 `https` URL
2. **DNS 解析检查**: 通过 `socket.getaddrinfo()` 解析目标主机名，检查 IP 是否属于私有/回环/链路本地/保留地址段
3. **Content-Type 校验**: 响应必须是 `image/*` 类型

### 路径遍历防护 (下载)

`/api/download/image` 端点验证用户提供的文件名:

1. **文件名白名单**: 正则 `^[\w\u4e00-\u9fff.\-]+$` 仅允许字母数字、中文、点和短横线
2. **路径包含检查**: `filepath.resolve().is_relative_to(save_dir.resolve())` 确保解析后的路径在目标目录内

### XSS 防护 (前端)

`useMarkdown.ts` 组合式函数对 Markdown 渲染进行消毒:

1. **HTML 实体转义**: 在 Markdown 解析前转义所有 `<`、`>`、`&`
2. **危险协议过滤**: 中和 `javascript:`、`data:`、`vbscript:` 链接
3. **安全外部链接**: 为所有外部链接添加 `rel="noopener noreferrer"` + `target="_blank"`

## 账单

### 费用计算
- `calc_cost(provider, tokens_in, tokens_out, call_count)` 在 `billing_service.py` 中 — 统一计费公式
  - `per_token`: `unit_price × (tokens_in + tokens_out) / 1000` (无 token 数据时回退到 `unit_price × call_count`)
  - `per_call`: `unit_price × call_count`
- `record_billing()` 在 `billing_service.py` 中 — 创建账单记录的单一入口
- 所有账单记录使用 `provider.billing_type.value` (不再硬编码)

### 操作类型 (detail.type)
| Type | 标签 | 路径 |
|---|---|---|
| `image_gen` | 图像生成 | `handle_generate` |
| `optimize` | 提示词优化 | `optimize_prompt`, `optimize_prompt_stream` |
| `assistant` | 小助手对话 | `stream_llm_chat` (stream_type="assistant") |
| `plan` | 规划生成 | `stream_llm_chat` (stream_type="plan") 通过 `/api/prompt/plan` |
| `vision` | 视觉分析 | `_describe_reference_images` |
| `agent` | Agent执行 | `run_agent_loop` (最终账单) |
| `tool` | 工具调用 | `run_agent_loop` (每次工具调用账单, 如 web_search) |

### 图像生成
- 按调用计费: call_count = image_count
- 按 token 计费: 使用 chat_edit API 返回的 token 用量
- 图生图: chat_edit 走 Chat API 计费 (per_token), edit 走 Images API

### LLM 服务
- 提示词优化、规划、助手对话均按 token 计费，提取 API usage
- 视觉兜底按 token 计费
- 通过 `/api/prompt/stream` 和 `/api/prompt/plan` (SSE) 流式调用
- 账单记录在 `prompt_optimizer.py` 和 `generate_service.py` 中创建

### 明细 API
- `GET /api/billing/breakdown` 按提供商和操作类型分组返回费用
- 前端账单抽屉同时显示两个表格 (API 支出 + 操作类型明细)

## Agent 系统

Agent 系统通过 Function Calling 提供 LLM 驱动的自主工具编排。

### 架构

```
用户输入 (Agent 模式)
    │
    ▼
┌──────────────────────────────────────┐
│              AgentLoop               │
│  LLM Chat → 检测 tool_calls →        │
│  执行工具 → 注入结果 →               │
│  循环直到 finish_reason=stop          │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│              工具注册表               │
│  web_search → Serper API            │
│  image_search → Serper API          │
│  generate_image → ImageClient       │
│  plan → plan_template_service       │
└──────────────────────────────────────┘
```

### 工具 (backend/app/tools/)
- **base.py**: `Tool` 抽象类 + `ToolResult` 数据类
- **web_search.py** / **image_search.py**: Serper.dev 集成，内部 3 次重试
- **generate_image.py**: 封装 ImageClient，count 限制为 1
- **plan.py**: 封装 plan_template_service CRUD + 模板匹配

### AgentLoop (backend/app/services/agent_service.py)
- `run_agent_loop()`: 异步生成器，产出 `AgentEvent` 类型 (TokenEvent, ToolCallEvent, ToolResultEvent, DoneEvent, CancelledEvent, WarningEvent)
- `tool_choice`: 第 0-1 轮为 `"required"` (强制早期至少调用一次工具)，第 2 轮起为 `"auto"`
- 工具提供商注入: web_search 和 image_gen API 密钥解密后传递给工具执行
- 按轮计费 (LLM) + 每次工具调用计费
- 取消支持: 每会话 `asyncio.Event`
- Checkpoint 超时: `wait_checkpoint()` 默认 300 秒，超时自动拒绝

### 辐射策略流程
对于多项目生成 (如 "3 个表情包")，通过两条路径处理:

1. **直接路由** (主要): `handle_agent_generate()` 检测 "套图/表情包/系列/组" 关键词且数量 >= 2 → 通过关键词匹配或正则回退提取子项 → 直接调用 `_execute_radiate()`，完全绕过 LLM Agent Loop
2. **Agent Loop 兜底**: LLM 调用 `plan(action="apply")` 套图模板 → 从 plan 工具结果触发 `_execute_radiate()`

`_execute_radiate()` 流程:
3. 生成锚点网格 → PIL 裁剪为单元格 → 逐单元格使用 `chat_edit()` 生图

### SSE 事件
| 事件 | 数据 |
|------|------|
| `token` | `{type:"token", content:"..."}` |
| `tool_call` | `{type:"tool_call", name:"web_search", args:{query:"..."}}` |
| `tool_result` | `{type:"tool_result", name:"web_search", content:"...", meta:{...}}` |
| `tool_warning` | `{type:"tool_warning", name:"web_search", reason:"重试耗尽"}` |
| `checkpoint` | `{type:"checkpoint", step:"anchor_grid", image_url:"..."}` |
| `done` | `{type:"done", usage:{tokens_in, tokens_out}}` |

## 并发模型

- 后端: 使用 asyncio 的 async/await
- 数据库: aiosqlite 用于异步 SQLite
- TaskManager 单例: 全局任务状态 + SSE 广播给所有连接客户端
- 图像生成: `asyncio.Semaphore` 用于速率限制
- 前端: SSE EventSource 用于实时任务状态 (snapshot + task_update + ping)，无需 WebSocket
- 多会话: activeTasks Map 支持跨多个会话并发生成

## 配置

| 设置 | 默认值 | 位置 |
|------|--------|------|
| `DATA_DIR` | `./data` | `config.py` |
| `DB_URL` | `sqlite+aiosqlite:///data/lamimager.db` | `config.py` |
| `MAX_CONCURRENT_TASKS` | 5 | `config.py` / app_settings |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | `config.py` |

## 部署

### 环境要求
- Python 3.14+ (标准 GIL 模式，非自由线程 `python3.14t`)
- Node.js 18+

### 开发环境
- 前端: Vite 开发服务器，端口 5173
- 后端: Uvicorn，端口 8000
- Vite 代理将 `/api` 转发到后端

### 生产环境
- 构建前端: `npm run build` → `frontend/dist/`
- FastAPI 从 `frontend/dist/` 提供静态文件
- 单进程同时处理 API 和静态文件
