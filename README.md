# LamImager

AI Image Generation Manager - A full-stack application for AI image generation with LLM-powered planning and optimization.

## Features

- **Conversation-based UI** - Chat interface with session management
- **Real-time Status** - SSE event stream for live task status across sessions
- **Multi-session Concurrency** - Run generation/optimization/planning across multiple sessions simultaneously
- **LLM Streaming** - Real-time streaming responses via SSE
- **Reference Images** - Upload images as base64 references for img2img generation
- **Multiple API Support** - OpenAI-compatible LLM and Image Generation APIs
- **LLM Assistant** - Sidebar dialog for prompt optimization and planning
- **Plan Templates** - Reusable plan templates with variable substitution, auto-scanning, and AI-assisted generation
- **File Attachments** - Upload images and documents to enhance prompts
- **Skill System** - Reusable prompt templates with parameters
- **Rule Engine** - Global filters and default parameters
- **Billing Tracking** - Per-call and per-token cost tracking

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.14+ / FastAPI / SQLAlchemy (async) / aiosqlite |
| Frontend | Vue3 / TypeScript / Pinia / Vue Router / Vite |
| Database | SQLite (single file, AES-256-GCM encrypted keys) |
| UI | Lucide Icons, minimalist black/white/gray palette |

## Quick Start

### Prerequisites

- Python 3.14+
- Node.js 18+

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Production Build

```bash
cd frontend
npm run build
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The built frontend is automatically served by FastAPI at the root path.

## Project Structure

```
LamImager/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI entry point
│   │   ├── config.py        # Global configuration
│   │   ├── database.py      # SQLAlchemy async setup
│   │   ├── models/          # 9 data models
│   │   ├── routers/         # 10 API routers (45+ endpoints)
│   │   ├── services/        # Business logic layer (11 services)
│   │   ├── schemas/         # Pydantic request/response
│   │   └── utils/           # Crypto, LLM client, Image client
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/           # 8 page components
│   │   ├── api/             # 11 API client modules
│   │   ├── stores/          # Pinia state management
│   │   ├── types/           # TypeScript definitions
│   │   └── styles/          # Global CSS (black/white/gray)
│   └── package.json
├── data/                    # Runtime data (SQLite, uploads)
└── docs/                    # Documentation
```

## API Endpoints

### Sessions
- `GET/POST /api/sessions` - List/create sessions
- `POST /api/sessions/{id}/generate` - Generate images (with reference_images, context_messages, plan_strategy)
- `GET /api/sessions/events` - SSE real-time task status

### Prompt
- `POST /api/prompt/optimize` - Optimize prompt (5 directions + custom)
- `POST /api/prompt/optimize/stream` - Stream optimization via SSE
- `POST /api/prompt/stream` - Stream LLM chat (SSE)

### Plan Templates
- `GET/POST /api/plan-templates` - List/create templates
- `POST /api/plan-templates/{id}/apply` - Apply template with variable substitution

### Providers
- `GET/POST /api/providers` - Manage API providers
- `POST /api/providers/{id}/test` - Test connection

### Billing
- `GET /api/billing/summary` - Cost summary

### Skills, Rules, References
- Full CRUD at `/api/skills`, `/api/rules`, `/api/references`

## Configuration

Environment variables (optional):

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `true` | Enable debug mode |
| `DEFAULT_IMAGE_SIZE` | `1024x1024` | Default image dimensions |
| `LAMIMAGER_DATA_DIR` | `<project>/data` | Override runtime data directory |
| `LAMIMAGER_STATIC_DIR` | `<project>/frontend/dist` | Override frontend static files directory |

## License

MIT
