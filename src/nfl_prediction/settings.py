"""Environment-backed settings for local development."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NFL_", env_file=".env", extra="ignore")

    host: Literal["127.0.0.1", "localhost", "::1"] = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    display_timezone: Literal["America/Chicago"] = "America/Chicago"

    data_dir: Path = Path("data")
