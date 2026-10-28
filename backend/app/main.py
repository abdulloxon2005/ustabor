from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.services.storage import UPLOADS_DIR

_is_prod = settings.ENVIRONMENT == "production"

app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version="0.1.0",
    description="UstaBor MVP: mijoz va usta o'rtasidagi buyurtma platformasi",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_PREFIX)

UPLOADS_DIR.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=str(UPLOADS_DIR)), name="media")


@app.get("/", include_in_schema=False)
def root():
    return {"app": settings.APP_NAME, "docs": None if _is_prod else "/docs"}
