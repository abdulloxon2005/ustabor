#!/usr/bin/env bash
# Konteyner har safar ishga tushganda: avval migratsiyalarni qo'llaydi,
# so'ng asosiy buyruqni (uvicorn) ishga tushiradi.
set -e

echo "Migratsiyalar qo'llanmoqda (alembic upgrade head)..."
alembic upgrade head

exec "$@"
