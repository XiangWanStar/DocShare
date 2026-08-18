"""文件管理：上传 / 列表 / 详情 / 下载 / 删除（开发计划 M3）。"""
from pathlib import Path

from fastapi import APIRouter, Depends, File as FileParam, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import File, User
from ..schemas import FileOut
from ..services.auth import get_current_user, get_optional_user
from ..services.share import validate_office_download_token
from ..services.storage import delete_file as delete_storage_file
from ..services.storage import file_exists, save_upload
from ..utils.security import now_utc
from ..utils.tokens import generate_file_id
from ..utils.urls import request_base

router = APIRouter(prefix="/api/files", tags=["files"])


def _get_owned_file(db: Session, file_id: str, user: User) -> File:
    file = db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="文件不存在")
    if file.owner_id != user.id:
        raise HTTPException(status_code=403, detail="无权操作该文件")
    return file


@router.post("/upload", response_model=FileOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = FileParam(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or "").name
    ext = Path(filename).suffix.lower()
    if not ext or ext not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型，仅允许: {', '.join(settings.allowed_extensions)}")

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(status_code=413, detail="文件超过大小限制")

    file_id = generate_file_id()
    storage_path = save_upload(user.id, file_id, filename, content)
    db_file = File(
        id=file_id,
        owner_id=user.id,
        filename=filename,
        storage_path=str(storage_path),
        mime_type=file.content_type,
        file_size=len(content),
        version=1,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    return db_file


@router.get("", response_model=list[FileOut])
def list_files(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    files = db.scalars(
        select(File).where(File.owner_id == user.id).order_by(File.created_at.desc())
    ).all()
    result = []
    for f in files:
        item = FileOut.model_validate(f)
        item.download_url = f"{request_base(request)}/api/files/{f.id}/download"
        result.append(item)
    return result


@router.get("/{file_id}", response_model=FileOut)
def get_file(
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = _get_owned_file(db, file_id, user)
    return file


@router.get("/{file_id}/download")
def download_file(
    file_id: str,
    office_token: str | None = None,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """下载文件。

    - 登录用户（文件所有者）：直接下载；
    - OnlyOffice Document Server：携带 office_token 下载（无用户会话）。
    """
    if validate_office_download_token(office_token, file_id):
        file = db.get(File, file_id)
        if not file or not file_exists(file.storage_path):
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(
            file.storage_path,
            media_type=file.mime_type or "application/octet-stream",
            filename=file.filename,
        )

    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    file = _get_owned_file(db, file_id, user)
    if not file_exists(file.storage_path):
        raise HTTPException(status_code=404, detail="文件已丢失")
    return FileResponse(
        file.storage_path,
        media_type=file.mime_type or "application/octet-stream",
        filename=file.filename,
    )


@router.post("/{file_id}/star", response_model=FileOut)
def toggle_star(
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """收藏/取消收藏当前文件。"""
    file = _get_owned_file(db, file_id, user)
    file.starred = not file.starred
    db.commit()
    db.refresh(file)
    return file


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file = _get_owned_file(db, file_id, user)
    delete_storage_file(file.storage_path)
    db.delete(file)
    db.commit()
    return None