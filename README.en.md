# LamImager

AI Image Generation Manager — a full-stack desktop application for AI-powered image generation with conversation-based UI, LLM planning, and real-time streaming.

## Features

**Core Workflow**
- Conversation-based chat interface with session management
- Upload reference images (base64) for img2img generation
- Refine mode: selectively re-generate from generated images
- Context image auto-population with pin/remove support

**AI Assistance**
- LLM sidebar assistant for prompt optimization and planning
- Prompt optimization via 5 directions + custom, streamed via SSE
- Plan templates with variable substitution and AI-assisted generation
- Plan strategy support during session generation

**Real-time Streaming**
- SSE (Server-Sent Events) for live task status across all sessions
- Token-by-token streaming for LLM chat, optimization, and planning
- Multi-session concurrency: generate/optimize/plan across sessions simultaneously

**Management**
- API provider management with encrypted keys (AES-256-GCM)
- Skill system: reusable prompt templates with parameters
- Rule engine: global filters and default parameters
- Billing tracking: per-call and per-token cost tracking with CSV export
- Dashboard with session/image/generation stats

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.14+ / FastAPI / SQLAlchemy (async) / aiosqlite |
| Frontend | Vue3 / TypeScript / Pinia / Vue Router / Vite |
| Desktop | PyInstaller + pywebview (Windows) |
| Database | SQLite (single file) |
| UI | Lucide Icons, BW-gray palette |

## Quick Start

### Prerequisites

- Python 3.14+
- Node.js 18+

### Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` — the Vite dev server proxies `/api` to the backend.

### Production

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

FastAPI serves the built frontend at the root path.

### Desktop App

```bash
python build.py
```

This packages the entire app into a standalone Windows executable via PyInstaller + pywebview. Output: `dist/LamImager/`.

## Project Structure

```
LamImager/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI entry point
│       ├── config.py            # Settings (DATA_DIR, DB_URL, CORS)
│       ├── database.py          # Async SQLAlchemy setup
│       ├── models/              # SQLAlchemy models (9 tables)
│       ├── routers/             # FastAPI routers (11 modules)
│       ├── services/            # Business logic (15 services)
│       ├── schemas/             # Pydantic request/response models
│       └── utils/               # crypto, llm_client, image_client
├── frontend/
│   └── src/
│       ├── views/               # 8 page components (Sessions.vue is main)
│       ├── api/                 # Axios API clients (12 modules)
│       ├── stores/              # Pinia stores (provider, billing, session)
│       ├── composables/         # Reusable composables (useSessionEvents, useDialog, useMarkdown, useDownload)
│       └── types/               # TypeScript interfaces
├── desktop/                     # Desktop app (PyInstaller + pywebview)
├── docs/                        # Architecture, API reference, runbook
│   ├── api-reference.md
│   ├── architecture.md
│   └── runbook.md
└── data/                        # Runtime data (SQLite, uploads)
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `true` | Enable debug mode |
| `DEFAULT_IMAGE_SIZE` | `1024x1024` | Default image dimensions |
| `LAMIMAGER_DATA_DIR` | `<project>/data` | Override runtime data directory |
| `LAMIMAGER_STATIC_DIR` | `<project>/frontend/dist` | Override frontend static files directory |

## Documentation

- [API Reference](docs/api-reference.md) — full API documentation
- [Architecture](docs/architecture.md) — data model, workflows, tiers
- [Runbook](docs/runbook.md) — deployment and troubleshooting

## Author

霖二 [@Laaaaaaaam](https://github.com/Laaaaaaaam)

## License

MIT
