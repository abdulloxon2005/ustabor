from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "UstaBor"
    ENVIRONMENT: str = "development"
    API_PREFIX: str = "/api/v1"

    # SQLite hozir, keyin PostgreSQL: faqat shu qiymat o'zgaradi
    DATABASE_URL: str = "sqlite:///./ustabor.db"

    # Majburiy: defolt qiymat yo'q, .env da bo'lishi shart
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Vergul bilan ajratilgan ro'yxat
    CORS_ORIGINS: str = "http://localhost:5500,http://127.0.0.1:5500"

    # Standart komissiya foizi (buyurtma yaratilganda orderga nusxalanadi)
    COMMISSION_RATE: int = 10

     # Faqat seed skript uchun (productionda .env orqali o'zgartiring)
    SEED_ADMIN_PHONE: str = "+998900000000"
    SEED_ADMIN_PASSWORD: str = "admin12345"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()