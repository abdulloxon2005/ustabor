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
    # Narx taklifi uchun maksimal chegara (so'mda)
    QUOTE_MAX_PRICE: int = 100_000_000

     # Faqat seed skript uchun (productionda .env orqali o'zgartiring)
    SEED_ADMIN_PHONE: str = "+998900000000"
    SEED_ADMIN_PASSWORD: str = "admin12345"

    # ===== Takliflar va moslashtirish (matching) =====
    # Taklif amal qilish muddati (daqiqa)
    OFFER_TTL_MINUTES: int = 30

    # Bayes o'rtacha reytingi uchun prior: m (pseudo-sharh soni)
    MATCH_RATING_PRIOR_COUNT: int = 5
    # Sharhlar bazasida hech narsa yo'q bo'lganda global o'rtacha sifatida ishlatiladigan qiymat
    MATCH_DEFAULT_GLOBAL_AVG: float = 4.0
    # "Yangi usta" chegarasi: rating_count < shu qiymat = yangi
    MATCH_NEW_MASTER_THRESHOLD: int = 3

    # Scoring vaznlari (har biri 0..1 oralig'ida, yig'indisi 1 bo'lishi shart emas)
    MATCH_W_RATING: float = 0.6    # Bayes reyting
    MATCH_W_DISTRICT: float = 0.25  # Tuman mos kelishi
    MATCH_W_NEW_BONUS: float = 0.15 # Yangi usta bonusi

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
