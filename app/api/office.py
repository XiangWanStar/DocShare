"""OnlyOffice 编排：在线打开配置生成、保存回调（开发计划 M5）。"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import File, Share, User
from ..services.auth import get_current_user
from ..services.onlyoffice import build_document_config, handle_callback
from ..services.share import (
    build_office_download_token,
    get_share_from_access_token,
    get_share_by_token,
    is_share_expired,
)
from ..utils.urls import office_base

router = APIRouter(tags=["office"])


def _check_onlyoffice_configured():
    if not settings.is_onlyoffice_configured():
        raise HTTPException(
            status_code=503,
            detail="OnlyOffice Document Server 未配置，请联系管理员",
        )


@router.get("/api/office/status")
def office_status():
    return {
        "configured": settings.is_onlyoffice_configured(),
        "onlyofficeUrl": settings.onlyoffice_url.rstrip("/") if settings.onlyoffice_url else "",
        "publicBaseUrl": settings.public_base_url,
        "jwtEnabled": settings.onlyoffice_jwt_enabled,
    }


@router.get("/api/office/config/{file_id}")
def office_config(
    file_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """登录用户（文件所有者）在线打开配置：可编辑。"""
    _check_onlyoffice_configured()
    file = db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    if file.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该文件")

    base = office_base(request)
    download_url = (
        f"{base}/api/files/{file.id}/download"
        f"?office_token={build_office_download_token(file.id)}"
    )
    callback_url = f"{base}/onlyoffice/callback"
    config = build_document_config(
        file,
        mode="edit",
        user={"id": user.id, "name": user.name or user.email},
        download_url=download_url,
        callback_url=callback_url,
    )
    return {"config": config, "onlyofficeUrl": settings.onlyoffice_url.rstrip("/")}


@router.get("/api/office/share/{token}")
def office_share_config(
    token: str,
    request: Request,
    share: Share = Depends(get_share_from_access_token),
):
    """分享访问者在线打开配置：按分享权限决定 只读/可编辑。"""
    _check_onlyoffice_configured()
    file = share.file
    mode = "edit" if share.permission == "edit" else "view"

    base = office_base(request)
    download_url = (
        f"{base}/s/{token}/download"
        f"?office_token={build_office_download_token(file.id, share_token=token)}"
    )
    callback_url = f"{base}/onlyoffice/callback"
    config = build_document_config(
        file,
        mode=mode,
        user={"id": f"visitor-{share.token[:8]}", "name": "访客"},
        download_url=download_url,
        callback_url=callback_url,
    )
    return {"config": config, "onlyofficeUrl": settings.onlyoffice_url.rstrip("/")}


@router.post("/onlyoffice/callback")
async def onlyoffice_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """OnlyOffice 保存回调（对应开发计划 8.4 节）。"""
    try:
        body = await request.json()
    except Exception:
        return {"error": 1}
    return await handle_callback(db, body)