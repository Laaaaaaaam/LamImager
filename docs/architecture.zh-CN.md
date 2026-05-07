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
│  │ (9 个模块)  │  │ (9 个服务)  │  │ (8 张表)    │        │
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
| Services | 业务逻辑，外部 API 调用 | `app/services/*.py` |
| Models | SQLAlchemy ORM 定义 | `app/models/*.py` |
| Schemas | Pydantic 验证/序列化 | `app/schemas/*.py` |
| Utils | 加密，LLM 客户端，图像客户端 | `app/utils/*.py` |

### 前端 (Vue3)

| 组件 | 用途 | 文件 |
|------|------|------|
| Views | 页面组件 | `src/views/*.vue` |
| API 客户端 | Axios HTTP 客户端 | `src/api/*.ts` |
| Stores | Pinia 状态管理 | `src/stores/*.ts` |
| Types | TypeScript 接口 | `src/types/index.ts` |

## 数据模型

| 模型 | 用途 |
|------|------|
| `api_providers` | API 配置 (LLM + 图像生成)，加密密钥 |
| `skills` | 可复用的提示词模板 |
| `rules` | 全局配置规则 (default_params/filter/workflow) |
| `billing_records` | 每次 API 调用的费用追踪 (关联到会话) |
| `reference_images` | 参考图片元数据，包含强度/裁剪配置 |
| `sessions` | 聊天式 UI 的会话 |
| `messages` | 会话内的消息 (user/assistant/system) |
| `app_settings` | 应用设置 (默认提供商，图片尺寸) |

## 数据流

### 基于会话的生成流程

```
用户输入 (可选附件 + 参考图片)
    │
    ▼
┌──────────────────┐
│ Sessions.vue     │  带文件上传的聊天输入 (base64)
│                  │  发送 context_messages (最近 10 条消息)
└────────┬─────────┘
         │ POST /api/sessions/{id}/generate
         │  { prompt, reference_images, context_messages }
         ▼
┌──────────────────┐
│ session.py router│  验证输入，创建消息
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ generate_service │  应用技能/规则，注入上下文
│                  │  将 reference_images 传递给 ImageClient
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ ImageClient      │  图生图三级降级:
│                  │  ① chat_edit() → /v1/chat/completions (多模态)
│                  │  ② edit()      → /v1/images/edits (原生)
│                  │  ③ generate()  → /v1/images/generations (文字兜底，通过 Vision LLM)
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

## 账单

### 图像生成
- 按调用计费: 每张图片固定费用
- 按 token 计费: 基于输入/输出 token 的费用

### LLM 服务
- 提示词优化、LLM 规划、助手对话
- 费用 = unit_price × (tokens_in + tokens_out) / 1000
- 账单记录在 `prompt_optimizer.py` 和 `generate_service.py` 中创建
- 通过 `/api/prompt/stream` 流式调用，在 `stream_llm_chat()` 中计费

## 并发模型

- 后端: 使用 asyncio 的 async/await
- 数据库: aiosqlite 用于异步 SQLite
- 图像生成: `asyncio.Semaphore` 用于速率限制
- 前端: 标准 Vue 响应式，无 WebSocket (轮询)

## 配置

| 设置 | 默认值 | 位置 |
|------|--------|------|
| `DATA_DIR` | `./data` | `config.py` |
| `DB_URL` | `sqlite+aiosqlite:///data/lamimager.db` | `config.py` |
| `MAX_CONCURRENT_TASKS` | 5 | `config.py` |
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
