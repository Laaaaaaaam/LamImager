# LamImager Runbook

## Quick Start

### Development Mode

```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm install
npm run dev
```

Access: http://localhost:5173

### Production Mode

```bash
# Build frontend
cd frontend
npm run build

# Start server
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Access: http://localhost:8000

---

## Health Checks

### Backend Health
```bash
curl http://localhost:8000/api/health
# Expected: {"status": "ok", "version": "0.1.0"}
```

### Database Check
```bash
ls -la data/lamimager.db
# Should exist and be readable
```

### Frontend Build Check
```bash
ls -la frontend/dist/
# Should contain index.html and assets/
```

---

## Configuration

### API Providers
Configure in UI at **API 配置** page or via API:

**LLM Provider**: OpenAI-compatible `/v1/chat/completions` endpoint
**Image Provider**: OpenAI-compatible `/v1/images/generations` endpoint  
**Web Search Provider**: Serper.dev (配置方式：API管理 → 新建 → 类型选 `联网搜索` → 填写 Serper API Key)

| Provider Type | ui label | API URL | Required |
|---------------|----------|---------|----------|
| `llm` | LLM | OpenAI-compatible | Yes |
| `image_gen` | 图像生成 | OpenAI-compatible | Yes |
| `web_search` | 联网搜索 | https://google.serper.dev | For agent search |

### Settings
Settings page configures: default providers, image size (W×H), max concurrent tasks, **search retry count** (default 3).

---

## Common Operations

### Reset Database

```bash
# Stop the server first
rm data/lamimager.db
# Restart server - tables will be recreated automatically
```

### Clear Uploads

```bash
rm -rf data/uploads/*
```

### Export Billing Data

```bash
curl "http://localhost:8000/api/billing/export" -o billing.csv
```

---

## Troubleshooting

### Backend won't start

1. Check Python version: `python --version` (need 3.14+)
2. Check dependencies: `pip install -r requirements.txt`
3. Check port availability: `netstat -an | grep 8000`
4. Check logs for errors
5. On some Linux distros, `sqlite3` may not be bundled with Python 3.14 — install via `apt install python3.14-sqlite`

### Frontend build fails

1. Check Node version: `node --version` (need 18+)
2. Clear node_modules: `rm -rf node_modules && npm install`
3. Check TypeScript errors: `npx vue-tsc --noEmit`
4. If vue-tsc fails, try: `npx vite build` (skip type checking)

### API calls fail with CORS

1. Check `CORS_ORIGINS` in `backend/app/config.py`
2. Ensure frontend dev server is on port 5173
3. Check browser console for specific CORS errors

### Database locked errors

1. Ensure only one server instance is running
2. Check for zombie processes: `ps aux | grep uvicorn`
3. Restart the server

### API key encryption fails

1. The encryption key is derived from machine fingerprint
2. If moving to a new machine, API keys need to be re-entered
3. Check `app/utils/crypto.py` for key derivation logic

---

## Logs

### Enable Debug Logging

Set in `backend/app/config.py`:
```python
DEBUG = True
LOG_LEVEL = "DEBUG"
```

### Log Location

- Default: Console output
- Configurable: `LOG_FILE` in config.py

---

## Backup

### Backup Database
```bash
cp data/lamimager.db data/lamimager.db.backup
```

### Backup Uploads
```bash
tar -czf uploads-backup.tar.gz data/uploads/
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `true` | Enable debug mode |
| `DEFAULT_IMAGE_SIZE` | `1024x1024` | Default image size |
| `LAMIMAGER_DATA_DIR` | `<project>/data` | Override runtime data directory (DB, uploads, logs) |
| `LAMIMAGER_STATIC_DIR` | `<project>/frontend/dist` | Override static files directory |

### Config File

Location: `backend/app/config.py`

Key settings:
- `DATA_DIR`: Runtime data directory (default `<project>/data`, overridable via `LAMIMAGER_DATA_DIR`)
- `DB_URL`: SQLite connection string (auto-derived from `DATA_DIR`)
- `CORS_ORIGINS`: Allowed frontend origins
- `UPLOAD_DIR`: File upload directory (under `DATA_DIR`)
- `STATIC_DIR`: Frontend static files (overridable via `LAMIMAGER_STATIC_DIR`)

---

## Monitoring

### Check Monthly Costs

```bash
curl http://localhost:8000/api/billing/summary
```

### Check API Providers

```bash
curl http://localhost:8000/api/providers
```
