__author__ = "霖二 @Laaaaaaaam"
__copyright__ = "Copyright (c) 2026 霖二 @Laaaaaaaam"
__license__ = "MIT"
__email__ = "2667605815@qq.com"

import ipaddress
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiohttp
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from app.config import settings
from app.database import init_db
from app.routers import api_provider, prompt, skill, rule, billing, reference, dashboard, session, settings as settings_router, plan_template, download


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_provider.router)
app.include_router(prompt.router)
app.include_router(skill.router)
app.include_router(rule.router)
app.include_router(billing.router)
app.include_router(reference.router)
app.include_router(dashboard.router)
app.include_router(session.router)
app.include_router(settings_router.router)
app.include_router(plan_template.router)
app.include_router(download.router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "author": settings.APP_AUTHOR,
        "license": "MIT",
    }


@app.get("/api/migration-status")
async def migration_status():
    from app.config import settings

    db_path = settings.DATA_DIR / "lamimager.db"
    app_empty = not db_path.exists() or db_path.stat().st_size < 50 * 1024

    source_dir = _find_legacy_data_dir()
    legacy_has_data = source_dir is not None

    return {
        "can_migrate": app_empty and legacy_has_data,
        "app_empty": app_empty,
        "legacy_has_data": legacy_has_data,
        "source_dir": str(source_dir) if source_dir else None,
        "target_dir": str(settings.DATA_DIR),
    }


@app.post("/api/import-data")
async def import_data():
    import shutil
    from app.config import settings

    source_dir = _find_legacy_data_dir()
    if source_dir is None:
        return {"success": False, "message": "未找到旧版本数据"}

    target_dir = settings.DATA_DIR
    source_db = source_dir / "lamimager.db"
    target_db = target_dir / "lamimager.db"

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source_db), str(target_db))
    source_uploads = source_dir / "uploads"
    target_uploads = target_dir / "uploads"
    if source_uploads.exists():
        if target_uploads.exists():
            shutil.rmtree(str(target_uploads))
        shutil.copytree(str(source_uploads), str(target_uploads))
    return {"success": True, "message": "数据导入成功，请重启应用以生效"}


def _find_legacy_data_dir():
    import sys
    from pathlib import Path
    from app.config import settings, _get_default_data_dir

    candidates = []

    if not getattr(sys, "frozen", False):
        candidates.append(_get_default_data_dir())

    candidates.append(Path.home() / "LamImager" / "data")

    for d in candidates:
        db = d / "lamimager.db"
        if db.exists() and db.stat().st_size > 1024:
            return d
    return None


static_dir: Path = settings.STATIC_DIR

@app.get("/api/images/proxy")
async def proxy_image(url: str):
    decoded = unquote(url)
    parsed = urlparse(decoded)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only HTTP/HTTPS URLs are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        resolved_ip = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for family, *_, sockaddr in resolved_ip:
            addr = ipaddress.ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                raise HTTPException(status_code=403, detail="Access to private/internal addresses is not allowed")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(decoded, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail=f"Upstream returned {resp.status}")
                content = await resp.read()
                content_type = resp.headers.get("Content-Type", "image/png")
                if not content_type.startswith("image/"):
                    raise HTTPException(status_code=403, detail="Only image content types are allowed")
                return Response(content=content, media_type=content_type)
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")

if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        if request.url.path.startswith("/api"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(static_dir / "index.html")

    @app.get("/")
    async def root():
        return FileResponse(static_dir / "index.html")
