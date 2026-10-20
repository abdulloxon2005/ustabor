from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.models.enums import Role

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = "Avtorizatsiya talab qilinadi"
_FORBIDDEN = "Bu amal uchun ruxsat yo'q"


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Token tekshiriladi, foydalanuvchi va roli HAR SAFAR bazadan o'qiladi."""
    if credentials is None:
        raise _unauthorized()
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise _unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def require_role(*roles: Role | str):
    allowed = {Role(r) for r in roles}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=_FORBIDDEN
            )
        return user

    return checker
