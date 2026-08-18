"""密码哈希、JWT 签发与校验。"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from ..config import settings

# pbkdf2_hmac 参数
_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16


def now_utc() -> datetime:
    """返回 naive UTC 当前时间（SQLite 存储用）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    """使用 PBKDF2-HMAC-SHA256 哈希密码，格式：pbkdf2_sha256$iter$salt_hex$hash_hex。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = password_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def create_token(subject: str, expires_minutes: int, extra: Optional[dict] = None) -> str:
    """签发 JWT。subject 放入 'sub'，extra 合并进 payload。"""
    now = now_utc()
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.get_jwt_secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """校验并解析 JWT，失败返回 None。"""
    try:
        return jwt.decode(token, settings.get_jwt_secret(), algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
