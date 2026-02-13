from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field(..., alias="DATABASE_URL")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
    sql_echo: bool = Field(False, alias="SQL_ECHO")

    dashboard_debounce_seconds: float = Field(2.0, alias="DASHBOARD_DEBOUNCE_SECONDS")


settings = Settings()

