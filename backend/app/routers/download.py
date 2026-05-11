import asyncio
import os
import sys
from pathlib import Path

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.settings_service import get_setting

router = APIRouter(prefix="/api/download", tags=["download"])


class DownloadImageRequest(BaseModel):
    url: str
    filename: str = "image.png"


def get_default_download_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path.cwd()
    return base / "downloads"


@router.get("/default-path")
async def default_download_path():
    return {"path": str(get_default_download_dir())}


@router.post("/image")
async def download_image(req: DownloadImageRequest, db: AsyncSession = Depends(get_db)):
    dir_value = await get_setting(db, "download_directory")
    if dir_value and dir_value.get("value"):
        save_dir = Path(dir_value["value"])
    else:
        save_dir = get_default_download_dir()

    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"无法创建目录 {save_dir}: {e}", "path": str(save_dir)},
        )

    if not save_dir.is_dir():
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"路径不是目录: {save_dir}", "path": str(save_dir)},
        )

    filepath = save_dir / req.filename
    resolved = filepath.resolve()
    if not str(resolved).startswith(str(save_dir.resolve())):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"非法文件路径: {filepath}"},
        )

    counter = 1
    stem = filepath.stem
    suffix = filepath.suffix
    while filepath.exists():
        filepath = save_dir / f"{stem} ({counter}){suffix}"
        counter += 1

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(req.url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return JSONResponse(
                        status_code=502,
                        content={"success": False, "error": f"图片服务器返回 HTTP {resp.status}", "upstream_status": resp.status},
                    )
                content = await resp.read()
    except aiohttp.ServerTimeoutError:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": "下载超时(30s)", "url": req.url},
        )
    except aiohttp.ClientConnectorError as e:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"无法连接到图片服务器: {e}", "url": req.url},
        )
    except aiohttp.ClientError as e:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": f"下载失败: {type(e).__name__}: {e}", "url": req.url},
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=502,
            content={"success": False, "error": "下载超时", "url": req.url},
        )

    try:
        filepath.write_bytes(content)
    except OSError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"无法写入文件 {filepath}: {e}", "path": str(filepath)},
        )

    return {"success": True, "path": str(filepath), "size": len(content)}
