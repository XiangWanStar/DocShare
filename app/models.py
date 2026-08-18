"""SQLAlchemy ORM 模型：users / files / shares（对应开发计划第 5 节）。"""
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .utils.security import now_utc


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=now_utc, nullable=False)

    files: Mapped[List["File"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    starred: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, default=now_utc, nullable=False)
    updated_at: Mapped[object] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc, nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="files")
    shares: Mapped[List["Share"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class Share(Base):
    __tablename__ = "shares"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(10), default="view", nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[object]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[object] = mapped_column(DateTime, default=now_utc, nullable=False)

    file: Mapped["File"] = relationship(back_populates="shares")