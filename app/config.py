"""Configuración global cargada desde .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Generador de Registros de Jornada"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8600
    APP_ENV: str = "development"

    DATABASE_URL: str = "sqlite:///./data/registro.db"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True,
    )


settings = Settings()
