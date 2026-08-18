"""OnlyOffice Document Server 编排：配置生成、回调处理（对应开发计划 8.3/8.4 节）。"""
import logging
from pathlib import Path
from typing import Optional

import httpx
import jwt
from sqlalchemy.orm import Session

from ..config import settings
from ..models import File
from ..utils.security import now_utc
from .storage import overwrite_document

logger = logging.getLogger(__name__)

# 扩展名 -> documentType 映射
_WORD_EXTS = {".doc", ".docx", ".docm", ".dot", ".dotx", ".dotm", ".odt", ".ott", ".rtf", ".txt", ".html", ".htm", ".md", ".epub", ".fb2", ".pages"}
_CELL_EXTS = {".xls", ".xlsx", ".xlsm", ".xlt", ".xltx", ".csv", ".ods", ".ets"}
_SLIDE_EXTS = {".ppt", ".pptx", ".pptm", ".pot", ".potx", ".pps", ".ppsx", ".odp"}
_PDF_EXTS = {".pdf", ".djvu", ".xps"}


def document_type_for(ext: str) -> str:
    ext = ext.lower()
    if ext in _CELL_EXTS:
        return "cell"
    if ext in _SLIDE_EXTS:
        return "slide"
    if ext in _PDF_EXTS:
        return "pdf"
    return "word"


def office_key(file: File) -> str:
    """OnlyOffice 文档 key：文件每次保存后必须变化，DS 据此判断是否需要重新保存。"""
    return f"{file.id}_{file.version}"


def parse_office_key(key: str) -> Optional[tuple[str, int]]:
    """从 key 解析出 (file_id, version)。"""
    if not key or "_" not in key:
        return None
    file_id, version_str = key.rsplit("_", 1)
    try:
        return file_id, int(version_str)
    except ValueError:
        return None


def sign_config(config: dict) -> dict:
    """对整个 config 做 JWT 签名（DS 开启 JWT_ENABLED 时校验）。"""
    if not settings.onlyoffice_jwt_enabled:
        return config
    config["token"] = jwt.encode(
        config, settings.get_onlyoffice_jwt_secret(), algorithm="HS256"
    )
    return config


def build_document_config(
    file: File,
    mode: str,
    user: dict,
    download_url: str,
    callback_url: str,
) -> dict:
    """生成 OnlyOffice 在线打开配置（对应开发计划 8.3 节）。"""
    ext = Path(file.filename).suffix.lower().lstrip(".")
    config = {
        "document": {
            "fileType": ext or "docx",
            "key": office_key(file),
            "title": file.filename,
            "url": download_url,
            "permissions": {
                "edit": mode == "edit",
                "download": True,
                "print": True,
            },
        },
        "documentType": document_type_for(Path(file.filename).suffix),
        "editorConfig": {
            "callbackUrl": callback_url,
            "mode": mode,
            "lang": "zh-CN",
            "user": {"id": user["id"], "name": user["name"]},
            "customization": {
                "autosave": True,
                "forcesave": True,
                "feedback": False,
                "compactHeader": False,
                "toolbarTabs": True,
            },
        },
    }
    return sign_config(config)


def verify_callback_token(body: dict) -> dict:
    """OnlyOffice 回调 body 可能带 token 字段（签名整个 body），校验并还原。"""
    if not settings.onlyoffice_jwt_enabled:
        return body
    token = body.get("token")
    if not token:
        # 未签名：仅在调试模式放行，否则拒绝
        if settings.debug:
            logger.warning("OnlyOffice 回调未携带 JWT token（调试模式放行）")
            return body
        raise ValueError("OnlyOffice 回调缺少 JWT token")
    return jwt.decode(
        token, settings.get_onlyoffice_jwt_secret(), algorithms=["HS256"]
    )


async def handle_callback(db: Session, body: dict) -> dict:
    """处理 OnlyOffice 保存回调（对应开发计划 8.4 节）。

    返回 DS 要求的 {"error": 0}。
    """
    try:
        body = verify_callback_token(body)
    except Exception as exc:
        logger.error("OnlyOffice 回调 token 校验失败: %s", exc)
        return {"error": 1}

    status = body.get("status")
    key = body.get("key") or ""

    if status == 1:
        # 用户连接/断开，无需处理
        return {"error": 0}
    if status == 4:
        # 关闭无修改
        return {"error": 0}
    if status in (3, 7):
        logger.error("OnlyOffice 保存出错 status=%s key=%s", status, key)
        return {"error": 0}

    if status in (2, 6):
        parsed = parse_office_key(key)
        if not parsed:
            logger.error("OnlyOffice 回调 key 无法解析: %s", key)
            return {"error": 1}
        file_id, version = parsed
        file = db.get(File, file_id)
        if not file:
            logger.error("回调对应文件不存在: %s", file_id)
            return {"error": 1}

        # 防旧回调覆盖新版本
        if version != file.version:
            logger.warning("忽略过期回调 key=%s (当前版本 %s)", key, file.version)
            return {"error": 0}

        url = body.get("url")
        if not url:
            logger.error("回调缺少下载地址 url (key=%s)", key)
            return {"error": 1}

        # 从 OnlyOffice 下载最新文档
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content

        overwrite_document(file.storage_path, content)
        file.version += 1
        file.updated_at = now_utc()
        file.file_size = len(content)
        db.commit()
        logger.info("文件已保存并升级版本: %s -> v%s", file.id, file.version)
        return {"error": 0}

    logger.warning("未知回调 status=%s", status)
    return {"error": 0}
