import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    APP_NAME: str = "LamImager"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = Path(os.environ.get("LAMIMAGER_DATA_DIR", "")) if os.environ.get("LAMIMAGER_DATA_DIR") else BASE_DIR / "data"
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
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if not self.DB_URL:
            self.DB_URL = f"sqlite+aiosqlite:///{self.DB_PATH}"


settings = Settings()
