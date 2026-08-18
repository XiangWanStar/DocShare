"""SQLAlchemy 引擎与会话管理。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# SQLite 需要 check_same_thread=False 以支持 FastAPI 线程池
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建数据库表（幂等）并执行轻量迁移。"""
    from . import models  # noqa: F401  确保模型已注册

    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """SQLite 轻量迁移：旧库补充新增列。"""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    if "files" in tables:
        cols = {c["name"] for c in insp.get_columns("files")}
        if "starred" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE files ADD COLUMN starred BOOLEAN NOT NULL DEFAULT 0"))
            import logging
            logging.getLogger(__name__).info("迁移: files 表已补充 starred 列")