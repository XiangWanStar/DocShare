"""Pydantic 请求/响应模型。"""
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer


# ---------- 用户 ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: Optional[str] = Field(default=None, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def _ser_dt(self, dt: datetime) -> str:
        return _iso_utc(dt)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- 文件 ----------
class FileOut(BaseModel):
    id: str
    filename: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    version: int
    starred: bool = False
    created_at: datetime
    updated_at: datetime
    download_url: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "updated_at")
    def _ser_dt(self, dt: datetime) -> str:
        return _iso_utc(dt)


# ---------- 分享 ----------
class ShareCreate(BaseModel):
    file_id: str
    permission: str = Field(default="view", pattern="^(view|edit)$")
    password: Optional[str] = Field(default=None, max_length=128)
    expires_at: Optional[datetime] = None


class ShareOut(BaseModel):
    id: str
    file_id: str
    token: str
    permission: str
    has_password: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    url: str
    filename: str

    model_config = {"from_attributes": True}

    @field_serializer("expires_at", "created_at")
    def _ser_dt(self, dt: Optional[datetime]):
        return _iso_utc(dt) if dt is not None else None


class ShareVerifyIn(BaseModel):
    password: Optional[str] = None


class ShareVerifyOut(BaseModel):
    ok: bool
    requires_password: bool = False
    access_token: Optional[str] = None
    message: Optional[str] = None


class ShareInfo(BaseModel):
    valid: bool
    expired: bool = False
    requires_password: bool = False
    permission: str = "view"
    filename: Optional[str] = None
    file_size: Optional[int] = None
    owner_name: Optional[str] = None
    message: Optional[str] = None


class Message(BaseModel):
    message: str

def _iso_utc(dt: datetime) -> str:
    """统一输出带 Z 的 UTC ISO 字符串，避免前端把 naive UTC 当作本地时间解析（时区偏移 bug）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")