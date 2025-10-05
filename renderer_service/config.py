"""Service configuration loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field, validator


class ServiceSettings(BaseModel):
    auth_token: Optional[str] = Field(default=None, alias="RENDER_AUTH_TOKEN")
    max_workers: Optional[int] = Field(default=None, alias="RENDER_MAX_WORKERS")
    temp_root: Optional[str] = Field(default=None, alias="RENDER_TEMP_ROOT")

    @validator("max_workers")
    def _validate_workers(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if value < 1:
            raise ValueError("max_workers must be >= 1")
        return value

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> ServiceSettings:
    data = {key: os.getenv(key) for key in ("RENDER_AUTH_TOKEN", "RENDER_MAX_WORKERS", "RENDER_TEMP_ROOT")}
    return ServiceSettings(**data)
