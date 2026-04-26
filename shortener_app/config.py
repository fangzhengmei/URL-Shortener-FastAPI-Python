# Configuration file

from functools import lru_cache
from typing import List

from pydantic import BaseSettings, validator


class Settings(BaseSettings):
    env_name: str = "Local"
    base_url: str = "http://localhost:8000"
    db_url: str = "sqlite:///./shortener.db"
    domains: List[str] = ["localhost:8000", "127.0.0.1:8000"]

    @validator("domains", pre=True)
    def parse_domains(cls, v):
        if isinstance(v, str):
            return [d.strip() for d in v.split(",")]
        return v

    class Config:
        env_file = "/Users/adrianadewunmi/PyCharm/GitHub_Projects/URL-Shortener-FastAPI-Python/.env"


@lru_cache
def get_settings() -> Settings:
    settings: Settings = Settings()
    print(f"Loading settings for: {settings.env_name}")
    print(f"Configured domains: {settings.domains}")
    return settings
