"""Configuración global cargada desde .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Generador de Registros de Jornada"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8600
    APP_ENV: str = "development"

    DATABASE_URL: str = "sqlite:///./data/registro.db"

    # Clave para firmar la cookie de sesión. Si rotas su valor, todas las
    # sesiones activas dejarán de ser válidas y los usuarios verán /login.
    SECRET_KEY: str

    # DNI del administrador inicial. Si no existe como usuario al arrancar,
    # se crea con es_admin=True. Si existe como usuario normal, se promueve.
    # Dejar vacío para omitir el bootstrap.
    ADMIN_DNI: str = ""

    SESSION_COOKIE_NAME: str = "registro_jornada_session"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True,
    )


settings = Settings()
