# core/config.py
from pathlib import Path
from typing import List
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).with_name(".env")

class Settings(BaseSettings):
    # App
    APP_NAME: str = "AskForge Backend"
    DEBUG: bool = False
    APP_PREFIX: str = "/api"
    APP_DESCRIPTION: str = "AskForge Backend - RAG + Question Generation APIs"

    # CORS
    CORS_ORIGINS: List[AnyHttpUrl] = []

    # Chunking
    CHUNK_SIZE: int = 1024
    CHUNK_OVERLAP: int = 300
    MIN_CHARS: int = 300

    # Storage
    PAGES_JSON_DIR: str = "data/user_db"

    # Chroma
    CHROMA_PERSIST_DIR: str = ".chroma"

    # Gemini (đặt required hoặc có default tuỳ bạn)
    GEMINI_API_KEY: str = Field(min_length=1)  # thiếu sẽ raise
    GEMINI_MODEL_NAME: str = Field(default="gemini-2.5-flash")

    # Ollama (embedding, question generation, optional chat)
    OLLAMA_BASE_URL: str = Field(default="http://localhost:11434")
    OLLAMA_EMBED_MODEL: str = Field(default="bge-m3")
    OLLAMA_QG_MODEL: str = Field(default="qwen2.5:3b")
    OLLAMA_CHAT_MODEL: str = Field(default="qwen2.5:7b")

    REDIS_URL: str = Field(default="redis://localhost:6379")
    # >>> Pydantic v2 config
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),          # chính xác: core/.env
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
