# LamImager Project Rules

## Tech Stack

- Backend: Python 3.14+ / FastAPI / SQLAlchemy async / aiosqlite
- Frontend: Vue3 / TypeScript / Pinia / Vue Router / Vite
- Database: SQLite (single file)
- API Style: OpenAI-compatible (LLM + Image Generation)

## Code Style

### Python (Backend)
- Python 3.14+ required (use `py -3.14` if multiple versions installed)
- Use async/await for all database operations
- Pydantic v2 with `model_config = ConfigDict(from_attributes=True)` or `class Config: from_attributes = True`
- SQLAlchemy 2.0 style with `Mapped[]` type hints
- AES-256-GCM encryption for sensitive data (API keys)
- Router -> Service -> Model three-layer architecture
- Python 3.14+ style: use `X | None` not `Optional[X]`, `list[X]` not `List[X]`, `dict[X, Y]` not `Dict[X, Y]` in type annotations
- Use `collections.abc.AsyncGenerator` not `typing.AsyncGenerator`
- Do NOT use `from __future__ import annotations` (deferred evaluation is default in 3.14)
- Do NOT use free-threaded mode (`python3.14t`)

### TypeScript (Frontend)
- Vue 3 Composition API with `<script setup lang="ts">`
- Pinia stores with `defineStore` and composition API
- Axios for API calls, base URL `/api`
- No emoji in UI - use Lucide icons

## UI Design Rules

- Color palette: #FAFAFA (bg), #FFFFFF (card), #E5E5E5 (border), #000000 (accent)
- No card stacking - use tables for data display
- Side drawers for forms, minimal modals
- Billing display: single line in topbar, expandable drawer
- No dark theme

## API Conventions

- All API routes prefixed with `/api`
- RESTful CRUD: GET/POST for list/create, GET/PUT/DELETE for item operations
- Return Pydantic models, not raw dicts
- Encrypt API keys before storage, mask in responses (show last 4 chars)

## Database

- SQLite file: `data/lamimager.db`
- UUID primary keys as strings
- JSON columns for arrays/objects (result_urls, parameters, config)
- Numeric type for costs/prices

## File Paths

- Backend code: `backend/app/`
- Frontend code: `frontend/src/`
- Runtime data: `data/`
- Uploads: `data/uploads/`
- Documentation: `docs/`

## Common Commands

```bash
# Backend (Python 3.14+ required)
cd backend && py -3.14 -m uvicorn app.main:app --reload

# Frontend dev
cd frontend && npm run dev

# Frontend build
cd frontend && npm run build
```
