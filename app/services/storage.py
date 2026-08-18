"""本地文件存储服务（对应开发计划 8.1 节）。"""
from pathlib import Path

from ..config import settings


def user_dir(user_id: str) -> Path:
    d = settings.files_dir / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_storage_path(user_id: str, file_id: str, ext: str) -> Path:
    """存储路径：data/files/{user_id}/{file_id}{ext}"""
    return user_dir(user_id) / f"{file_id}{ext}"


def save_upload(user_id: str, file_id: str, filename: str, content: bytes) -> Path:
    ext = Path(filename).suffix.lower()
    path = build_storage_path(user_id, file_id, ext)
    path.write_bytes(content)
    return path


def overwrite_document(storage_path: str, content: bytes) -> None:
    """OnlyOffice 保存回调：覆盖原文件。"""
    Path(storage_path).write_bytes(content)


def delete_file(storage_path: str) -> None:
    p = Path(storage_path)
    if p.exists():
        p.unlink()


def file_exists(storage_path: str) -> bool:
    return Path(storage_path).exists()
