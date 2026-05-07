# LamImager

AI 图像生成管理器 - 一个全栈 AI 图像生成应用，支持 LLM 驱动的规划和优化。

## 功能特性

- **对话式界面** - 带会话管理的聊天界面
- **LLM 流式输出** - 通过 SSE 实现实时流式响应
- **参考图片** - 上传图片作为 base64 参考进行 img2img 生成
- **多 API 支持** - 兼容 OpenAI 的 LLM 和图像生成 API
- **LLM 助手** - 侧边栏对话，支持提示词优化和规划
- **文件附件** - 上传图片和文档增强提示词
- **技能系统** - 可复用的提示词模板，支持参数
- **规则引擎** - 全局过滤器和默认参数
- **账单追踪** - 按调用和按 token 的费用追踪

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.14+ / FastAPI / SQLAlchemy (async) / aiosqlite |
| 前端 | Vue3 / TypeScript / Pinia / Vue Router / Vite |
| 数据库 | SQLite (单文件，AES-256-GCM 加密密钥) |
| UI | Lucide 图标，极简黑白灰配色 |

## 快速开始

### 环境要求

- Python 3.14+
- Node.js 18+

### 后端设置

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端设置

```bash
cd frontend
npm install
npm run dev
```

### 生产构建

```bash
cd frontend
npm run build
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

构建后的前端由 FastAPI 在根路径自动提供。

## 项目结构

```
LamImager/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口
│   │   ├── config.py        # 全局配置
│   │   ├── database.py      # SQLAlchemy async 设置
│   │   ├── models/          # 8 个数据模型
│   │   ├── routers/         # 9 个 API 路由 (40+ 端点)
│   │   ├── services/        # 业务逻辑层 (9 个服务)
│   │   ├── schemas/         # Pydantic 请求/响应
│   │   └── utils/           # 加密、LLM 客户端、图像客户端
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/           # 7 个页面组件
│   │   ├── api/             # 9 个 API 客户端模块
│   │   ├── stores/          # Pinia 状态管理
│   │   ├── types/           # TypeScript 定义
│   │   └── styles/          # 全局 CSS (黑白灰)
│   └── package.json
├── data/                    # 运行时数据 (SQLite, 上传文件)
└── docs/                    # 文档
```

## API 端点

### 会话
- `GET/POST /api/sessions` - 列出/创建会话
- `POST /api/sessions/{id}/generate` - 生成图片 (支持 reference_images, context_messages)

### 提示词
- `POST /api/prompt/optimize` - 优化提示词
- `POST /api/prompt/stream` - 流式 LLM 对话 (SSE)

### 提供商
- `GET/POST /api/providers` - 管理 API 提供商
- `POST /api/providers/{id}/test` - 测试连接

### 账单
- `GET /api/billing/summary` - 费用汇总

### 技能、规则、参考图
- `/api/skills`, `/api/rules`, `/api/references` 完整 CRUD

## 配置

环境变量 (可选):

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEBUG` | `true` | 启用调试模式 |
| `DEFAULT_IMAGE_SIZE` | `1024x1024` | 默认图片尺寸 |
| `LAMIMAGER_DATA_DIR` | `<project>/data` | 覆盖运行时数据目录 |
| `LAMIMAGER_STATIC_DIR` | `<project>/frontend/dist` | 覆盖前端静态文件目录 |

## 许可证

MIT
