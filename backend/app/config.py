import os
import platform
import shutil
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_platform_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "LamImager"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "LamImager"
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(base) / "LamImager"


def _get_default_data_dir() -> Path:
    base_dir = Path(__file__).resolve().parent.parent.parent
    return base_dir / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    APP_NAME: str = "LamImager"
    APP_VERSION: str = "0.3.1beta"
    APP_AUTHOR: str = "霖二 @Laaaaaaaam"
    APP_AUTHOR_EMAIL: str = "2667605815@qq.com"
    DEBUG: bool = True

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    DATA_DIR: Path = Path(os.environ.get("LAMIMAGER_DATA_DIR", "")) if os.environ.get("LAMIMAGER_DATA_DIR") else _get_platform_data_dir()
    STATIC_DIR: Path = Path(os.environ.get("LAMIMAGER_STATIC_DIR", "")) if os.environ.get("LAMIMAGER_STATIC_DIR") else BASE_DIR / "frontend" / "dist"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    DB_PATH: Path = DATA_DIR / "lamimager.db"

    DB_URL: str = ""
    API_PREFIX: str = "/api"

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost", "http://127.0.0.1"]

    MAX_CONCURRENT_TASKS: int = 5
    DEFAULT_IMAGE_SIZE: str = "1024x1024"

    LOG_LEVEL: str = "INFO"
    LOG_FILE: Path = DATA_DIR / "lamimager.log"

    def model_post_init(self, __context):
        self._migrate_legacy_data()
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if not self.DB_URL:
            self.DB_URL = f"sqlite+aiosqlite:///{self.DB_PATH}"

    def _migrate_legacy_data(self):
        if os.environ.get("LAMIMAGER_DATA_DIR"):
            return
        legacy_dir = _get_default_data_dir()
        legacy_db = legacy_dir / "lamimager.db"
        new_db = self.DB_PATH
        if new_db.exists():
            return
        if legacy_db.exists() and legacy_db.stat().st_size > 1024:
            self.DATA_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(legacy_db), str(new_db))
            legacy_uploads = legacy_dir / "uploads"
            if legacy_uploads.exists():
                new_uploads = self.DATA_DIR / "uploads"
                if new_uploads.exists():
                    shutil.rmtree(str(new_uploads))
                shutil.copytree(str(legacy_uploads), str(new_uploads))


settings = Settings()
