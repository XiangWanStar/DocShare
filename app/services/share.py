"""分享链接服务。"""
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import File, Share, User
from ..utils.security import (
    create_token,
    decode_token,
    hash_password,
    now_utc,
    verify_password,
)
from ..utils.tokens import generate_share_id, generate_share_token
from .auth import bearer_scheme

PERMISSION_VIEW = "view"
PERMISSION_EDIT = "edit"


def create_share(
    db: Session,
    user: User,
    file_id: str,
    permission: str,
    password: Optional[str],
    expires_at: Optional[datetime],
) -> Share:
    file = db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    if file.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该文件")

    share = Share(
        id=generate_share_id(),
        file_id=file_id,
        token=generate_share_token(),
        permission=permission,
        password_hash=hash_password(password) if password else None,
        expires_at=expires_at,
        created_by=user.id,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share


def get_share_by_token(db: Session, token: str) -> Optional[Share]:
    return db.scalar(select(Share).where(Share.token == token))


def is_share_expired(share: Share) -> bool:
    return share.expires_at is not None and share.expires_at < now_utc()


def check_share_password(share: Share, password: Optional[str]) -> bool:
    """无密码直接通过；有密码则校验。"""
    if not share.password_hash:
        return True
    return verify_password(password or "", share.password_hash)


def build_share_access_token(share: Share) -> str:
    """分享访问凭证：短时 JWT，用于换取 OnlyOffice 配置。"""
    return create_token(
        "share",
        settings.share_access_token_expire_minutes,
        {"scope": "share", "share_token": share.token},
    )


def get_share_from_access_token(
    token: str,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Share:
    """FastAPI 依赖：校验分享访问 JWT，返回未过期的分享。"""
    forbidden = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="访问已失效，请重新验证")
    if credentials is None:
        raise forbidden
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("scope") != "share" or payload.get("share_token") != token:
        raise forbidden
    share = get_share_by_token(db, token)
    if not share or is_share_expired(share):
        raise forbidden
    return share


def build_office_download_token(file_id: str, share_token: Optional[str] = None) -> str:
    """OnlyOffice 下载令牌：供 Document Server 无登录下载文档，有效期 15 分钟。"""
    return create_token(
        "office",
        15,
        {"scope": "office_download", "file_id": file_id, "share_token": share_token},
    )


def validate_office_download_token(token: Optional[str], file_id: str, share_token: Optional[str] = None) -> bool:
    if not token:
        return False
    payload = decode_token(token)
    if not payload or payload.get("scope") != "office_download":
        return False
    if payload.get("file_id") != file_id:
        return False
    if share_token is not None and payload.get("share_token") != share_token:
        return False
    return True
