# Configuration file

import secrets
from functools import lru_cache
from typing import Optional

from pydantic import BaseSettings


class Settings(BaseSettings):
    env_name: str = "Local"
    base_url: str = "http://localhost:8000"
    db_url: str = "sqlite:///./shortener.db"

    jwt_secret_key: str = secrets.token_urlsafe(32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    allow_public_registration: bool = False
    invite_code: Optional[str] = None
    min_password_length: int = 6

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    settings: Settings = Settings()
    print(f"Loading settings for: {settings.env_name}")
    print(f"  - Public registration: {'Enabled' if settings.allow_public_registration else 'Disabled'}")
    if settings.invite_code:
        print(f"  - Invite code required: Yes")
    print(f"  - Min password length: {settings.min_password_length}")
    return settings
