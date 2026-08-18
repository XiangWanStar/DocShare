"""分享链接：创建/管理/公开访问（开发计划 M4）。"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import File, Share, User
from ..schemas import ShareCreate, ShareInfo, ShareOut, ShareVerifyIn, ShareVerifyOut
from ..services.auth import get_current_user
from ..services.share import (
    build_share_access_token,
    check_share_password,
    create_share,
    get_share_by_token,
    is_share_expired,
    validate_office_download_token,
)
from ..services.storage import file_exists
from ..utils.security import now_utc
from ..utils.urls import request_base
from datetime import timezone

router = APIRouter(tags=["shares"])


def _share_to_out(share: Share, db: Session, request: Request) -> ShareOut:
    return ShareOut(
        id=share.id,
        file_id=share.file_id,
        token=share.token,
        permission=share.permission,
        has_password=bool(share.password_hash),
        expires_at=share.expires_at,
        created_at=share.created_at,
        url=f"{request_base(request)}/s/{share.token}",
        filename=share.file.filename,
    )


def _get_owned_share(db: Session, share_id: str, user: User) -> Share:
    share = db.get(Share, share_id)
    if not share:
        raise HTTPException(status_code=404, detail="分享不存在")
    if share.file.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该分享")
    return share


# ---------- 管理接口（需登录） ----------
@router.post("/api/shares", response_model=ShareOut, status_code=status.HTTP_201_CREATED)
def create_share_api(
    data: ShareCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    expires_at = data.expires_at
    if expires_at is not None:
        # 统一转为 naive UTC 再入库
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
        if expires_at <= now_utc():
            raise HTTPException(status_code=400, detail="有效期必须晚于当前时间")
    share = create_share(
        db, user, data.file_id, data.permission, data.password, expires_at
    )
    return _share_to_out(share, db, request)


@router.get("/api/shares", response_model=list[ShareOut])
def list_shares(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    shares = db.scalars(
        select(Share)
        .join(File, Share.file_id == File.id)
        .where(File.owner_id == user.id)
        .order_by(Share.created_at.desc())
    ).all()
    return [_share_to_out(s, db, request) for s in shares]


@router.get("/api/shares/{share_id}", response_model=ShareOut)
def get_share(
    share_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return _share_to_out(_get_owned_share(db, share_id, user), db, request)


@router.delete("/api/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_share(
    share_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    share = _get_owned_share(db, share_id, user)
    db.delete(share)
    db.commit()
    return None


# ---------- 公开接口 ----------
@router.get("/s/{token}/info", response_model=ShareInfo)
def share_info(token: str, db: Session = Depends(get_db)):
    share = get_share_by_token(db, token)
    if not share or not file_exists(share.file.storage_path):
        return ShareInfo(valid=False, message="分享不存在或文件已删除")
    if is_share_expired(share):
        return ShareInfo(
            valid=False, expired=True, message="分享链接已过期",
            filename=share.file.filename,
        )
    return ShareInfo(
        valid=True,
        requires_password=bool(share.password_hash),
        permission=share.permission,
        filename=share.file.filename,
        file_size=share.file.file_size,
        owner_name=share.file.owner.name,
    )


@router.post("/s/{token}/verify", response_model=ShareVerifyOut)
def share_verify(
    token: str,
    data: ShareVerifyIn,
    db: Session = Depends(get_db),
):
    share = get_share_by_token(db, token)
    if not share:
        raise HTTPException(status_code=404, detail="分享不存在")
    if is_share_expired(share):
        raise HTTPException(status_code=403, detail="分享链接已过期")
    if not check_share_password(share, data.password):
        raise HTTPException(status_code=403, detail="访问密码错误")
    return ShareVerifyOut(
        ok=True,
        requires_password=bool(share.password_hash),
        access_token=build_share_access_token(share),
    )


@router.get("/s/{token}/download")
def share_download(
    token: str,
    office_token: str | None = None,
    db: Session = Depends(get_db),
):
    """公开下载（仅供 OnlyOffice Document Server 用 office_token 拉取）。"""
    share = get_share_by_token(db, token)
    if not share or not file_exists(share.file.storage_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    if is_share_expired(share):
        raise HTTPException(status_code=403, detail="分享链接已过期")
    if not validate_office_download_token(office_token, share.file_id, share_token=token):
        raise HTTPException(status_code=403, detail="无效的下载令牌")
    return FileResponse(
        share.file.storage_path,
        media_type=share.file.mime_type or "application/octet-stream",
        filename=share.file.filename,
    )


@router.get("/s/{token}", include_in_schema=False)
def share_page(token: str):
    """分享落地页：重定向到 SPA 分享路由。"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/static/vue/#/share/{token}")