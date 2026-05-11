# LamImager

AI 图像生成管理器 — 全栈桌面应用，支持 AI 驱动图像生成、对话式界面、LLM 规划与实时流式输出。

## 光速开始
在 [Release](https://github.com/Laaaaaaaam/LamImager/releases) 提供了 zip 下载文件，直接解压点击解压好的 exe 程序就能运行。

## 功能特性

**核心工作流**
- 对话式聊天界面，支持会话管理
- 上传参考图片（base64）进行 img2img 生成
- 精修模式：从已生成图片中选择目标重新生成
- 上下文图片自动填充，支持固定/移除

**AI 辅助**
- LLM 侧边栏助手，支持提示词优化与规划
- 提示词优化：5 种方向 + 自定义，通过 SSE 流式输出
- 计划模板：支持变量替换与 AI 辅助生成
- 会话生成时支持计划策略

**Agent 智能模式**
- 智能意图识别：自动区分单图、套图、多图、迭代精修等场景
- Function Calling 驱动：LLM 自主调用生图、搜索、规划工具
- 实时 SSE 事件流：逐 token 流式输出 + 工具调用可视化
- 套图辐射策略：锚点网格图 → 裁切 → 逐项精细生成
- 人机协作检查点：关键步骤确认后继续执行

**实时流式**
- SSE（Server-Sent Events）跨会话实时任务状态推送
- LLM 对话、优化、规划均支持逐 token 流式输出
- 多会话并发：可同时在多个会话中生成/优化/规划

**管理功能**
- API 提供商管理，密钥 AES-256-GCM 加密
- 技能系统：可复用的提示词模板，支持参数
- 规则引擎：全局过滤器与默认参数
- 账单追踪：按调用和按 token 计费，支持 CSV 导出
- 仪表盘：会话/图片/生成次数统计

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.14+ / FastAPI / SQLAlchemy (async) / aiosqlite |
| 前端 | Vue3 / TypeScript / Pinia / Vue Router / Vite |
| 桌面端 | PyInstaller + pywebview (Windows) |
| 数据库 | SQLite (单文件) |
| UI | Lucide 图标，黑白灰配色 |

## 快速开始

### 环境要求

- Python 3.14+
- Node.js 18+

### 开发环境

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173` — Vite 开发服务器会将 `/api` 代理到后端。

### 生产构建

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

FastAPI 在根路径自动提供构建后的前端文件。

### 桌面应用

```bash
python build.py
```

通过 PyInstaller + pywebview 将应用打包为独立的 Windows 可执行文件。输出目录：`dist/LamImager/`。

## 项目结构

```
LamImager/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI 入口
│       ├── config.py            # 全局配置 (DATA_DIR, DB_URL, CORS)
│       ├── database.py          # 异步 SQLAlchemy 配置
│       ├── models/              # SQLAlchemy 模型 (9 张表)
│       ├── routers/             # FastAPI 路由 (11 个模块)
│       ├── services/            # 业务逻辑层 (15 个服务)
│       ├── schemas/             # Pydantic 请求/响应模型
│       └── utils/               # crypto, llm_client, image_client
├── frontend/
│   └── src/
│       ├── views/               # 8 个页面组件 (Sessions.vue 为主页面)
│       ├── api/                 # Axios API 客户端 (12 个模块)
│       ├── stores/              # Pinia 状态管理 (provider, billing, session)
│       ├── composables/         # 可复用组合式函数 (useSessionEvents, useDialog, useMarkdown, useDownload)
│       └── types/               # TypeScript 类型定义
├── desktop/                     # 桌面应用 (PyInstaller + pywebview)
├── docs/                        # 架构、API 参考、运维手册
│   ├── api-reference.md
│   ├── architecture.md
│   └── runbook.md
└── data/                        # 运行时数据 (SQLite, 上传文件)
```

## 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEBUG` | `true` | 启用调试模式 |
| `DEFAULT_IMAGE_SIZE` | `1024x1024` | 默认图片尺寸 |
| `LAMIMAGER_DATA_DIR` | `<project>/data` | 覆盖运行时数据目录 |
| `LAMIMAGER_STATIC_DIR` | `<project>/frontend/dist` | 覆盖前端静态文件目录 |

## 文档

- [API 参考](docs/api-reference.zh-CN.md) — 完整 API 文档
- [架构说明](docs/architecture.zh-CN.md) — 数据模型、工作流、层级
- [运维手册](docs/runbook.zh-CN.md) — 部署与故障排查

## 作者

霖二 [@Laaaaaaaam](https://github.com/Laaaaaaaam)

## 许可证

MIT
