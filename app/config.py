"""应用配置。所有配置项可通过环境变量或 .env 文件覆盖。"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "DocShare - 轻量级 Word 在线查看/分享系统"
    debug: bool = True

    # ---- 数据库（第一阶段 SQLite，后续可切 PostgreSQL） ----
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"

    # ---- 本地文件存储 ----
    data_dir: Path = BASE_DIR / "data"

    # ---- JWT 鉴权 ----
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 登录 token 有效期 1 天
    share_access_token_expire_minutes: int = 60  # 分享访问 token 有效期 1 小时

    # ---- OnlyOffice Document Server ----
    # Document Server 地址（前端加载 api.js 用），留空表示未部署
    onlyoffice_url: str = ""
    onlyoffice_jwt_enabled: bool = True
    onlyoffice_jwt_secret: str = ""

    # 应用对外可访问的地址。留空则自动使用当前请求地址（本地联调）。
    # Docker/公网部署时 OnlyOffice 服务器需要能访问到下载/回调地址，
    # 必须显式配置为局域网 IP 或域名（不能是 localhost），详见 README。
    public_base_url: str = ""

    # ---- 上传限制 ----
    max_upload_size: int = 50 * 1024 * 1024  # 50MB
    allowed_extensions: list[str] = [
        ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
        ".pdf", ".txt", ".odt", ".rtf", ".csv",
    ]

    # ---- CORS ----
    cors_origins: list[str] = ["*"]

    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def db_path(self) -> Path:
        if self.database_url.startswith("sqlite:///"):
            return Path(self.database_url.replace("sqlite:///", "", 1))
        return self.data_dir / "app.db"

    def get_jwt_secret(self) -> str:
        """JWT 密钥：优先环境变量，否则持久化到 data/.jwt_secret（重启后 token 仍有效）。"""
        if self.jwt_secret:
            return self.jwt_secret
        secret_file = self.data_dir / ".jwt_secret"
        if secret_file.exists():
            return secret_file.read_text(encoding="utf-8").strip()
        import secrets
        secret = secrets.token_urlsafe(48)
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(secret, encoding="utf-8")
        return secret

    def get_onlyoffice_jwt_secret(self) -> str:
        """OnlyOffice JWT 密钥：未单独配置时复用应用 JWT 密钥。"""
        return self.onlyoffice_jwt_secret or self.get_jwt_secret()

    def is_onlyoffice_configured(self) -> bool:
        return bool(self.onlyoffice_url)


settings = Settings()