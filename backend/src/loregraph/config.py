from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CAMPAIGN_")

    data_dir: Path = Path("./data")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "campaign.sqlite3"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"
