from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings, loaded from environment variables and an optional .env file.
    """

    environment: str = "dev"
    port: int = 8080
    host: str = "0.0.0.0"

    # API Keys
    gemini_api_key: str = ""
    telegram_bot_token: str = ""

    # Firebase
    # Optional because in Cloud Run we might use Application Default Credentials
    firebase_credentials_path: str = ""
    firebase_project_id: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached instance of the application settings.
    """
    return Settings()


settings = get_settings()
