"""Configuração central do projeto via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações carregadas de variáveis de ambiente / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="RFQ_",
        extra="ignore",
    )

    # --- Caminhos ---
    cache_dir: Path = Field(default=Path.home() / ".rfquant" / "cache")
    db_path: Path = Field(default=Path.home() / ".rfquant" / "db.sqlite")

    # --- Dados ---
    brapi_token: str | None = Field(default=None, alias="BRAPI_TOKEN")
    brapi_base_url: str = "https://brapi.dev/api"

    # --- Logging ---
    log_level: str = "INFO"

    def ensure_dirs(self) -> None:
        """Cria os diretórios necessários, se não existirem."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_dirs()
