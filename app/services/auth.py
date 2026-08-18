"""用户鉴权服务：注册校验、登录、JWT 依赖。"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..utils.security import create_token, decode_token, verify_password

bearer_scheme = HTTPBearer(auto_error=False)


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def _resolve_user(credentials: Optional[HTTPAuthorizationCredentials], db: Session) -> Optional[User]:
    """从 Bearer JWT 解析用户；无凭证或凭证无效时返回 None。"""
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        return None
    return db.get(User, payload["sub"])


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI 依赖：解析 Authorization: Bearer <JWT> 并返回当前用户（必须登录）。"""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或登录已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = _resolve_user(credentials, db)
    if user is None:
        raise unauthorized
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """FastAPI 依赖：可选登录用户（未登录返回 None，供下载等场景使用）。"""
    return _resolve_user(credentials, db)