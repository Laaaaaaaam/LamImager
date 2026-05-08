# LamImager Architecture

## System Overview

LamImager is a monolithic web application for managing AI image generation tasks with a conversation-based UI. It combines a FastAPI backend (Python 3.14+) with a Vue3 frontend, using SQLite for data persistence.

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 Vue3 SPA (Vite)                      │   │
│  │  Pinia Stores ← API Clients (Axios)                  │   │
│  │  Sessions.vue (Main UI with Assistant Sidebar)       │   │
│  └──────────────────────┬──────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │ HTTP/REST
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Routers   │→ │  Services   │→ │   Models    │        │
│  │ (10 modules)│  │ (11 services)│  │ (9 tables) │        │
│  └─────────────┘  └─────────────┘  └──────┬──────┘        │
│                                           │                │
│  ┌────────────────────────────────────────┼──────────────┐ │
│  │              External APIs              │              │ │
│  │  LLM Client ──────► OpenAI-compatible LLM API         │ │
│  │  Image Client ────► OpenAI-compatible Image API       │ │
│  │  (chat_edit also uses /v1/chat/completions for img2img) │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     SQLite Database                         │
│  data/lamimager.db (AES-256-GCM encrypted API keys)        │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### Backend (FastAPI)

| Component | Purpose | Files |
|-----------|---------|-------|
| Routers | HTTP endpoint definitions | `app/routers/*.py` |
| Services | Business logic, external API calls | `app/services/*.py` |
| Models | SQLAlchemy ORM definitions | `app/models/*.py` |
| Schemas | Pydantic validation/serialization | `app/schemas/*.py` |
| Utils | Crypto, LLM client, Image client | `app/utils/*.py` |

### Frontend (Vue3)

| Component | Purpose | Files |
|-----------|---------|-------|
| Views | Page components | `src/views/*.vue` |
| API Clients | Axios HTTP clients | `src/api/*.ts` |
| Stores | Pinia state management | `src/stores/*.ts` |
| Types | TypeScript interfaces | `src/types/index.ts` |

## Data Models

| Model | Purpose |
|-------|---------|
| `api_providers` | API configurations (LLM + Image Gen), encrypted keys |
| `skills` | Reusable prompt templates |
| `rules` | Global configuration rules (default_params/filter/workflow) |
| `billing_records` | Cost tracking per API call (linked to sessions) |
| `reference_images` | Reference image metadata with strength/crop config |
| `sessions` | Conversation sessions for the chat-based UI |
| `messages` | Messages within sessions (user/assistant/system) |
| `app_settings` | Application settings (default providers, image size, max_concurrent) |
| `plan_templates` | Plan templates with variables for template-based planning |

## Data Flow

### Session-Based Generation Flow

```
User Input (with optional attachments + reference images)
    │
    ▼
┌──────────────────┐
│ Sessions.vue     │  Chat input with file upload (base64)
│                  │  contextImageList strip with numbered badges
│                  │  Sends context_messages with optional image_urls
└────────┬─────────┘
         │ POST /api/sessions/{id}/generate
         │  { prompt, reference_images, reference_labels, context_messages }
         ▼
┌──────────────────┐
│ session.py router│  Validates input, creates message
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ generate_service │  Applies skills/rules, builds multimodal context
│                  │  Passes reference_images to ImageClient
│                  │  reference_labels provide [图N] numbered mapping
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ ImageClient      │  Image-to-Image 3-tier fallback:
│                  │  Tier 1: chat_edit() → /v1/chat/completions (multimodal, numbered labels)
│                  │  Tier 2: edit()      → /v1/images/edits (native)
│                  │  Tier 3: Vision LLM  → /v1/images/generations (text-only)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Billing created  │  Cost recorded automatically
└──────────────────┘
```

**Iterative Refinement**: When using `plan_strategy: "iterative"`, the frontend fetches previous step outputs via `/api/images/proxy?url=` (server-side proxy, avoids CORS) and passes them as `reference_images` to the next step, enabling chained image-to-image refinement.

### LLM Assistant Flow (Streaming)

```
User Message (with optional attachments)
    │
    ▼
┌──────────────────┐
│ Sessions.vue     │  Assistant sidebar dialog / optimize / plan
└────────┬─────────┘
         │ POST /api/prompt/stream (SSE)
         ▼
┌──────────────────┐
│ stream_llm_chat  │  Calls LLM API with streaming
└────────┬─────────┘
         │ token by token (SSE)
         ▼
┌──────────────────┐
│ Frontend renders │  Real-time streaming display
└────────┬─────────┘
         │ [DONE] event
         ▼
┌──────────────────┐
│ Billing created  │  Token usage recorded
└──────────────────┘
```

## Security

### API Key Encryption

- Algorithm: AES-256-GCM
- Key derivation: SHA-256(MAC address + hostname)
- Storage: Base64(nonce + ciphertext + tag) in SQLite
- Response masking: Show only last 4 characters

### Encryption Flow

```python
# Encrypt
key = derive_key()  # From machine fingerprint
nonce = os.urandom(12)
ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
stored = base64.b64encode(nonce + ciphertext)

# Decrypt
combined = base64.b64decode(stored)
nonce, ciphertext = combined[:12], combined[12:]
plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
```

## Billing

### Cost Calculation
- `calc_cost(provider, tokens_in, tokens_out, call_count)` in `billing_service.py` — unified formula for all paths
  - `per_token`: `unit_price × (tokens_in + tokens_out) / 1000` (with fallback to `unit_price × call_count` when tokens unavailable)
  - `per_call`: `unit_price × call_count`
- `record_billing()` in `billing_service.py` — single entry point for creating billing records
- All billing records use `provider.billing_type.value` (no hardcoded `"per_token"`)

### Operation Types (detail.type)
| Type | Label | Path |
|---|---|---|
| `image_gen` | 图像生成 | `handle_generate` |
| `optimize` | 提示词优化 | `optimize_prompt`, `optimize_prompt_stream` |
| `assistant` | 小助手对话 | `stream_llm_chat` (stream_type="assistant") |
| `plan` | 规划生成 | `stream_llm_chat` (stream_type="plan") via `/api/prompt/plan` |
| `vision` | 视觉分析 | `_describe_reference_images` |

### Image Generation
- Per-call billing: Call count = image_count
- Per-token billing: Uses token usage from chat_edit API responses (Chat API returns usage; Images API does not)
- Image-to-image: chat_edit charges via Chat API (per-token), edit charges via Images API

### LLM Services
- Prompt optimization, planning, assistant dialog all use per-token billing with API usage extraction
- Vision fallback (image description) billed per token
- Streaming via `/api/prompt/stream` and `/api/prompt/plan` (SSE)
- Billing records created in `prompt_optimizer.py` and `generate_service.py`

### Session Cost Aggregation
- `list_sessions()` uses subqueries (`msg_subq` + `billing_subq`) to avoid cartesian product from dual OUTER JOINs
- Session `cost` = SUM of all billing records for that session
- Session `tokens` = SUM of all `tokens_in + tokens_out` for that session

### Breakdown API
- `GET /api/billing/breakdown` returns costs grouped by provider and by operation type
- Frontend billing drawer displays both tables (API spending + operation type breakdown)

## Agent System

The Agent system provides LLM-driven autonomous tool orchestration through Function Calling.

### Architecture

```
User Input (Agent mode)
    │
    ▼
┌──────────────────────────────────────┐
│              AgentLoop               │
│  LLM Chat → Detect tool_calls →      │
│  Execute tools → Inject results →    │
│  Loop until finish_reason=stop        │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│              Tool Registry            │
│  web_search → Serper API             │
│  image_search → Serper API           │
│  generate_image → ImageClient        │
│  plan → plan_template_service        │
└──────────────────────────────────────┘
```

### Tools (backend/app/tools/)
- **base.py**: `Tool` abstract class + `ToolResult` dataclass
- **web_search.py** / **image_search.py**: Serper.dev integration, internal 3x retry
- **generate_image.py**: Wraps ImageClient, supports `grid_config` for multi-item sets
- **plan.py**: Wraps plan_template_service CRUD + template matching

### AgentLoop (backend/app/services/agent_service.py)
- `run_agent_loop()`: async generator yielding `AgentEvent` types (TokenEvent, ToolCallEvent, ToolResultEvent, DoneEvent, CancelledEvent, WarningEvent)
- Tool provider injection: web_search and image_gen API keys decrypted and passed to tool execution
- Billing per round (LLM) + per tool call
- Cancel support: `asyncio.Event` per session

### Style Anchor Flow
For multi-item generation (e.g. "4 emoji pack"):
1. LLM → `plan(action="list")` → sees「套图生成」template
2. LLM → `plan(action="apply")` → triggers `_execute_radiate` in `generate_service.py`
3. Code generates anchor grid → PIL crops into cells → per-cell image generation with reference

### SSE Events
| Event | Data |
|-------|------|
| `token` | `{type:"token", content:"..."}` |
| `tool_call` | `{type:"tool_call", name:"web_search", args:{query:"..."}}` |
| `tool_result` | `{type:"tool_result", name:"web_search", content:"...", meta:{...}}` |
| `tool_warning` | `{type:"tool_warning", name:"web_search", reason:"retry exhausted"}` |
| `checkpoint` | `{type:"checkpoint", step:"anchor_grid", image_url:"..."}` |
| `done` | `{type:"done", usage:{tokens_in, tokens_out}}` |

## Concurrency Model

- Backend: Async/await with asyncio
- Database: aiosqlite for async SQLite
- TaskManager singleton: Global task state + SSE broadcast to all connected clients
- Image generation: `asyncio.Semaphore` for rate limiting
- Frontend: SSE EventSource for real-time task status (snapshot + task_update + ping), no WebSocket needed
- Multi-session: activeTasks Map enables concurrent generation across multiple sessions

## Configuration

| Setting | Default | Location |
|---------|---------|----------|
| `DATA_DIR` | `./data` | `config.py` |
| `DB_URL` | `sqlite+aiosqlite:///data/lamimager.db` | `config.py` |
| `MAX_CONCURRENT_TASKS` | 5 | `config.py` / app_settings |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | `config.py` |

## Deployment

### Requirements
- Python 3.14+ (standard GIL mode, NOT free-threaded `python3.14t`)
- Node.js 18+

### Development
- Frontend: Vite dev server on port 5173
- Backend: Uvicorn on port 8000
- Vite proxy forwards `/api` to backend

### Production
- Build frontend: `npm run build` → `frontend/dist/`
- FastAPI serves static files from `frontend/dist/`
- Single process handles both API and static files
