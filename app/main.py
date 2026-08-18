"""FastAPI 应用入口。"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, files, office, shares
from .config import settings
from .database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("数据库已初始化: %s", settings.db_path)
    if settings.is_onlyoffice_configured():
        logger.info("OnlyOffice Document Server: %s", settings.onlyoffice_url)
    else:
        logger.warning("OnlyOffice Document Server 未配置（设置 ONLYOFFICE_URL 环境变量启用在线编辑）")
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(files.router)
app.include_router(shares.router)
app.include_router(office.router)


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "app": settings.app_name}


@app.get("/go/{token}", include_in_schema=False)
def go_share(token: str):
    """旧分享入口重定向到 SPA 分享页。"""
    return RedirectResponse(f"/static/vue/#/share/{token}")


# 静态前端
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/static/vue/")