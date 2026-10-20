from fastapi import APIRouter

from app.api.v1 import admin, auth, categories, health, masters

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(categories.router)
api_router.include_router(masters.router)
api_router.include_router(admin.router)

# Keyingi kunlarda shu yerga qo'shiladi:
# api_router.include_router(orders.router)
