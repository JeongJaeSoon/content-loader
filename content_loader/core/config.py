"""Configuration management for content loader."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Database settings
    database_url: str = Field(
        default="sqlite:///./content_loader.db", description="Database connection URL"
    )

    # Redis settings
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching and task queue",
    )

    # API settings
    github_token: Optional[str] = Field(
        default=None, description="GitHub personal access token"
    )

    slack_bot_token: Optional[str] = Field(default=None, description="Slack bot token")

    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
