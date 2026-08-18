# DocShare · Code Wiki

> 轻量级 Word 在线查看/分享系统的结构化代码文档
>
> 本文基于对仓库源码的逐文件分析生成，覆盖整体架构、模块职责、关键类与函数、依赖关系与运行方式等关键信息。

---

## 目录

1. [项目概览](#1-项目概览)
2. [整体架构](#2-整体架构)
3. [技术栈与依赖](#3-技术栈与依赖)
4. [目录结构](#4-目录结构)
5. [核心数据模型](#5-核心数据模型)
6. [配置系统](#6-配置系统)
7. [数据库与会话管理](#7-数据库与会话管理)
8. [API 路由层](#8-api-路由层)
9. [服务层](#9-服务层)
10. [工具层](#10-工具层)
11. [OnlyOffice 集成流程](#11-onlyoffice-集成流程)
12. [安全模型](#12-安全模型)
13. [前端 SPA](#13-前端-spa)
14. [部署方式](#14-部署方式)
15. [测试体系](#15-测试体系)
16. [环境变量参考](#16-环境变量参考)

---

## 1. 项目概览

**DocShare** 是一个基于 FastAPI + SQLite + OnlyOffice Document Server 的轻量级文档管理系统，实现了《开发计划.md》中定义的 MVP 目标。

### 核心能力

- 用户注册 / 登录（JWT 鉴权）
- 上传、列表、下载、删除多格式 Office 文档（`.docx`/`.xlsx`/`.pptx`/`.pdf`/`.txt` 等）
- OnlyOffice 在线查看 / 编辑，保存后自动回写文件并升级版本
- 生成分享链接，支持：**只读 / 可编辑 / 密码保护 / 有效期**
- 未登录用户可通过分享链接在线查看文档
- 用户文件互相隔离（按 `owner_id` 分目录存储）

### 设计哲学

- **轻量优先**：第一阶段不引入 Redis / PostgreSQL / MinIO，使用 SQLite + 本地磁盘，降低部署与维护成本。
- **平滑迁移**：通过 SQLAlchemy 2.0 ORM 抽象数据库，后续切换 PostgreSQL 几乎无成本。
- **安全可控**：密码 PBKDF2 哈希、JWT 鉴权、OnlyOffice 回调验签、分享下载使用短时签名令牌。

---

## 2. 整体架构

### 2.1 分层架构

系统采用经典的四层架构，自上而下为：前端 SPA → API 路由层 → 服务层 → 数据/存储层。

```text
┌──────────────────────────────────────────────────────────┐
│  浏览器（Vue 3 SPA，静态托管于 /static/vue）              │
│  登录 / 注册 / 文件库 / OnlyOffice 查看 / 分享落地页       │
└────────────────────────────┬─────────────────────────────┘
                             │ HTTP + Bearer JWT
                             ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI 应用（app/main.py）                              │
│  ├─ API 路由层 app/api/   (auth / files / shares / office)│
│  └─ 静态文件挂载 /static、根路径重定向                    │
└────────────────────────────┬─────────────────────────────┘
                             │ 调用
                             ▼
┌──────────────────────────────────────────────────────────┐
│  服务层 app/services/                                      │
│  auth.py（鉴权依赖）/ storage.py（本地文件）              │
│  share.py（分享+令牌）/ onlyoffice.py（配置+回调）        │
└──────────┬──────────────────────────────┬───────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────┐        ┌──────────────────────────┐
│  工具层 app/utils/   │        │  OnlyOffice Document     │
│  security（密码+JWT）│        │  Server（独立容器）        │
│  tokens（ID 生成）   │        │  渲染/编辑 + 回调保存       │
│  urls（基地址）      │        └──────────────────────────┘
└──────────┬──────────┘                   ▲
           │                              │ httpx 下载新文档 + POST 回调
           ▼                              │
┌──────────────────────────────────────────────────────────┐
│  数据/存储层                                              │
│  SQLite (data/app.db) + 本地磁盘 (data/files/{user_id}/)  │
└──────────────────────────────────────────────────────────┘
```

### 2.2 关键请求流

**所有者在线编辑流：**

1. 浏览器请求 `GET /api/office/config/{file_id}`（带 JWT）
2. `office.py` 校验所有权 → `onlyoffice.py:build_document_config` 生成配置（含 `office_token` 下载链接与 `callbackUrl`）→ JWT 签名
3. 前端加载 DS 的 `api.js`，`new DocsAPI.DocEditor` 初始化编辑器
4. DS 用 `office_token` 调 `GET /api/files/{id}/download` 拉取文档
5. 用户编辑保存后，DS `POST /onlyoffice/callback` → `handle_callback` 下载最新文档 → `overwrite_document` 覆盖原文件 → `version += 1`

**分享访客查看流：**

1. 访客打开 `/s/{token}` → 重定向到 SPA 分享页
2. `GET /s/{token}/info` 获取分享信息（是否需要密码/过期/权限）
3. `POST /s/{token}/verify`（可能带密码）→ 返回短时 `access_token`
4. 前端用 `access_token` 请求 `GET /api/office/share/{token}` → 按分享权限生成只读/可编辑配置
5. DS 用 `office_token` 调 `GET /s/{token}/download` 拉取文档

---

## 3. 技术栈与依赖

### 3.1 后端依赖（`requirements.txt`）

| 依赖 | 用途 |
|---|---|
| `fastapi>=0.115` | Web 框架，路由、依赖注入、自动 OpenAPI 文档 |
| `uvicorn[standard]>=0.30` | ASGI 服务器 |
| `sqlalchemy>=2.0` | ORM（2.0 风格 `DeclarativeBase` + `Mapped`） |
| `pydantic[email]>=2.7` | 请求/响应模型校验（含 EmailStr） |
| `pydantic-settings>=2.3` | 基于 `.env` 的配置加载 |
| `PyJWT>=2.8` | 应用 JWT 与 OnlyOffice 配置签名（HS256） |
| `python-multipart>=0.0.9` | 文件上传（multipart/form-data） |
| `pytest>=8.0` | 单元/集成测试 |
| `httpx>=0.27` | 测试客户端 + OnlyOffice 回调中下载文档 |

### 3.2 运行时技术选型

| 模块 | 技术 |
|---|---|
| 后端 | Python 3.11+ / FastAPI |
| ORM | SQLAlchemy 2.0 |
| 数据库 | SQLite（`./data/app.db`，可平滑迁移 PostgreSQL） |
| 存储 | 本地磁盘（`./data/files/{user_id}/`） |
| 鉴权 | PyJWT（HS256） |
| 在线 Office | OnlyOffice Document Server |
| 前端 | Vue 3 SPA（腾讯文档风格三栏布局，`app/static/vue`） |
| 部署 | Docker Compose + Nginx |

---

## 4. 目录结构

```text
docx/
├── app/                         # 后端应用主包
│   ├── __init__.py
│   ├── main.py                  # FastAPI 入口：lifespan / 路由注册 / 静态挂载
│   ├── config.py                # Settings 配置类（环境变量 + .env）
│   ├── database.py              # SQLAlchemy 引擎 / 会话 / init_db / 迁移
│   ├── models.py                # ORM 模型：User / File / Share
│   ├── schemas.py               # Pydantic 请求/响应模型
│   ├── api/                     # API 路由层
│   │   ├── __init__.py
│   │   ├── auth.py              # 注册 / 登录 / 当前用户
│   │   ├── files.py             # 上传 / 列表 / 详情 / 下载 / 收藏 / 删除
│   │   ├── shares.py            # 创建/管理/公开分享接口
│   │   └── office.py            # OnlyOffice 配置 + 回调
│   ├── services/                # 业务服务层
│   │   ├── __init__.py
│   │   ├── auth.py              # 鉴权依赖（get_current_user 等）
│   │   ├── storage.py           # 本地文件存储
│   │   ├── share.py             # 分享创建 + 各类令牌签发/校验
│   │   └── onlyoffice.py        # OnlyOffice 配置生成 / 回调处理
│   ├── utils/                   # 工具层
│   │   ├── security.py          # 密码哈希 / JWT 签发与解析 / now_utc
│   │   ├── tokens.py            # 分享短码与文件 ID 生成
│   │   └── urls.py              # 请求基地址（用户视角 / DS 视角）
│   └── static/                  # 前端静态资源
│       ├── vue/                 # 生产 SPA（Vue 3 单文件应用）
│       │   ├── index.html
│       │   ├── app.js           # 单文件 Vue 应用
│       │   ├── styles.css
│       │   └── lib/             # vue.global.prod / vue-router.global.prod
│       └── svg/                 # 文件类型图标
├── tests/                       # 测试
│   ├── conftest.py              # pytest 全局 fixture + make_docx
│   ├── test_auth.py             # 鉴权单元测试
│   ├── test_files.py            # 文件管理测试
│   ├── test_shares.py           # 分享测试
│   ├── test_office.py           # OnlyOffice 集成测试
│   ├── e2e_live.py              # 端到端实测脚本（httpx）
│   ├── e2e_pages.py             # 静态页面可访问性脚本
│   ├── spa_flow.py              # Playwright SPA 全流程脚本
│   ├── ds_integration.py        # OnlyOffice 真机联调脚本
│   ├── ds_deep.py               # DS 命令服务 + 转换深度脚本
│   └── verify_fixes.py          # Bug 修复回归脚本
├── data/                        # 运行时数据（自动生成）
│   ├── app.db                   # SQLite 数据库
│   ├── .jwt_secret              # 自动生成的 JWT 密钥
│   └── files/{user_id}/{file_id}.ext
├── Dockerfile
├── docker-compose.yml           # app + onlyoffice 双容器
├── nginx.conf                   # 反向代理示例
├── pytest.ini
├── requirements.txt
├── .env / .env.example
├── ref_callback.md              # OnlyOffice 回调参考文档
├── ref_config.md                # OnlyOffice 配置参考文档
├── ref_signature.md             # OnlyOffice 签名参考文档
├── README.md
└── 开发计划.md                  # 完整开发计划（里程碑/数据库/API 设计）
```

---

## 5. 核心数据模型

### 5.1 ORM 模型（`app/models.py`）

三个表对应开发计划第 5 节设计，主键统一使用 32 位 hex（`secrets.token_hex(16)`）。

#### `User`（用户表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String(32) PK | 用户 ID |
| `email` | String(255) unique | 邮箱（注册时小写化） |
| `password_hash` | Text | PBKDF2-HMAC-SHA256 哈希 |
| `name` | String(100) nullable | 昵称 |
| `created_at` | DateTime | 创建时间（naive UTC） |
| `files` | relationship | 反向关联 `File`，级联删除 |

#### `File`（文件表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String(32) PK | 文件 ID |
| `owner_id` | String(32) FK→users.id | 所有者（级联删除） |
| `filename` | String(255) | 原始文件名 |
| `storage_path` | Text | 本地存储绝对路径 |
| `mime_type` | String(100) nullable | MIME 类型 |
| `file_size` | Integer nullable | 字节数 |
| `version` | Integer default=1 | 版本号（每次保存回调 +1） |
| `starred` | Boolean default=False | 收藏标记（迁移补充列） |
| `created_at` / `updated_at` | DateTime | 时间戳 |
| `owner` / `shares` | relationship | 反向关联 |

#### `Share`（分享表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String(32) PK | 分享 ID |
| `file_id` | String(32) FK→files.id | 关联文件（级联删除） |
| `token` | String(64) unique | 分享短码（`secrets.token_urlsafe(16)`） |
| `permission` | String(10) default="view" | `view` / `edit` |
| `password_hash` | Text nullable | 可选访问密码哈希 |
| `expires_at` | DateTime nullable | 过期时间（naive UTC） |
| `created_by` | String(32) FK→users.id | 创建者（删除置 NULL） |
| `created_at` | DateTime | 创建时间 |
| `file` | relationship | 反向关联 |

### 5.2 Pydantic 模型（`app/schemas.py`）

请求/响应模型，统一通过 `_iso_utc()` 序列化时间为带 `Z` 的 UTC ISO 字符串（修复前端时区误解析 bug）。

| 模型 | 用途 |
|---|---|
| `UserCreate` | 注册请求（email/password/name，密码 6-128 位） |
| `UserLogin` | 登录请求 |
| `UserOut` | 用户响应（`from_attributes`，序列化时间） |
| `TokenResponse` | 登录返回（`access_token` + `bearer`） |
| `FileOut` | 文件响应（含 `download_url` 可选字段） |
| `ShareCreate` | 分享创建请求（`permission` 正则约束 view/edit） |
| `ShareOut` | 分享响应（`has_password` 布尔 + `url` + `filename`） |
| `ShareVerifyIn` | 密码校验请求 |
| `ShareVerifyOut` | 校验结果（`ok`/`access_token`） |
| `ShareInfo` | 公开分享信息（`valid`/`expired`/`requires_password`） |
| `Message` | 通用消息 |

---

## 6. 配置系统

### 6.1 `Settings` 类（`app/config.py`）

继承 `pydantic_settings.BaseSettings`，通过 `model_config` 从项目根 `.env` 加载，`extra="ignore"` 忽略未知变量。全局单例 `settings = Settings()`。

```python
class Settings(BaseSettings):
    app_name: str = "DocShare - 轻量级 Word 在线查看/分享系统"
    debug: bool = True
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    data_dir: Path = BASE_DIR / "data"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24      # 登录 token 1 天
    share_access_token_expire_minutes: int = 60     # 分享访问 token 1 小时
    onlyoffice_url: str = ""
    onlyoffice_jwt_enabled: bool = True
    onlyoffice_jwt_secret: str = ""
    public_base_url: str = ""
    max_upload_size: int = 50 * 1024 * 1024         # 50MB
    allowed_extensions: list[str] = [".docx", ".doc", ".xlsx", ...]
    cors_origins: list[str] = ["*"]
```

### 6.2 关键方法

| 方法 | 说明 |
|---|---|
| `files_dir` (property) | `data_dir / "files"`，文件存储根目录 |
| `db_path` (property) | 从 `database_url` 解析 SQLite 路径 |
| `get_jwt_secret()` | 优先环境变量，否则读 `data/.jwt_secret`，不存在则生成并持久化（保证重启后 token 仍有效） |
| `get_onlyoffice_jwt_secret()` | 未单独配置时复用应用 JWT 密钥 |
| `is_onlyoffice_configured()` | `onlyoffice_url` 非空即视为已配置 |

---

## 7. 数据库与会话管理

`app/database.py` 负责引擎、会话工厂、建表与轻量迁移。

### 7.1 引擎与会话

```python
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass
```

- `check_same_thread=False`：允许 FastAPI 线程池跨线程使用 SQLite 连接。
- `expire_on_commit=False`：提交后对象仍可用，避免 `commit` 后访问属性触发额外查询。

### 7.2 依赖与初始化

| 函数 | 说明 |
|---|---|
| `get_db()` | FastAPI 依赖，每次请求生成一个 `Session`，`finally` 关闭 |
| `init_db()` | 创建 `db_path`/`files_dir` 目录 → `Base.metadata.create_all` → `_migrate()` |
| `_migrate()` | SQLite 轻量迁移：检测 `files` 表是否缺 `starred` 列，缺则 `ALTER TABLE` 补充 |

---

## 8. API 路由层

四个路由模块在 `app/main.py` 中通过 `app.include_router(...)` 注册。

### 8.1 `app/api/auth.py` — 用户鉴权（prefix `/api/auth`）

| 端点 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/register` | POST | 无 | 邮箱小写化查重 → 409；PBKDF2 哈希存库 → 201 |
| `/login` | POST | 无 | `authenticate_user` 校验 → 签发 JWT（有效期 1 天） |
| `/me` | GET | 必须 | 返回当前登录用户 |

关键函数：

- `register(data, db)`：注册，邮箱大小写不敏感查重，`name` 缺省取邮箱前缀。
- `login(data, db)`：调用 `authenticate_user`，失败 401，成功返回 `TokenResponse`。

### 8.2 `app/api/files.py` — 文件管理（prefix `/api/files`）

| 端点 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/upload` | POST | 必须 | multipart 上传，校验扩展名与大小，存盘 + 入库 |
| `` (空) | GET | 必须 | 列出当前用户文件，按创建时间倒序，附 `download_url` |
| `/{file_id}` | GET | 必须 | 文件详情（须为所有者） |
| `/{file_id}/download` | GET | 可选 | 所有者直接下载；DS 用 `office_token` 下载 |
| `/{file_id}/star` | POST | 必须 | 切换收藏状态 |
| `/{file_id}` | DELETE | 必须 | 删除文件 + 删除磁盘文件 |

关键函数：

- `_get_owned_file(db, file_id, user)`：统一的所有权校验辅助，不存在 404，非所有者 403。
- `upload_file()`：校验扩展名（白名单）→ 读内容 → 校验大小（50MB）→ `save_upload` 存盘 → 建 `File` 记录。
- `download_file()`：双路径——`office_token` 合法直接放行（供 DS 无会话下载）；否则要求登录且为所有者。

### 8.3 `app/api/shares.py` — 分享（tags `shares`）

分为**管理接口（需登录）**与**公开接口**两组。

| 端点 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/api/shares` | POST | 必须 | 创建分享，校验所有权 + 有效期晚于现在 |
| `/api/shares` | GET | 必须 | 我的分享列表（join File 过滤所有者） |
| `/api/shares/{share_id}` | GET | 必须 | 分享详情（须为所有者） |
| `/api/shares/{share_id}` | DELETE | 必须 | 撤销分享 → 204 |
| `/s/{token}/info` | GET | 无 | 公开信息（valid/expired/requires_password） |
| `/s/{token}/verify` | POST | 无 | 密码校验 → 返回短时 `access_token` |
| `/s/{token}/download` | GET | 无 | 仅 `office_token` 拉取（供 DS） |
| `/s/{token}` | GET | 无 | 落地页，重定向到 SPA `/#/share/{token}` |

关键函数：

- `_share_to_out(share, db, request)`：组装 `ShareOut`，`url` 用 `request_base(request)` 生成（跟随请求地址，不硬编码）。
- `_get_owned_share(...)`：所有权校验。
- `share_info()`：无密码直接返回信息；过期返回 `expired=True`。
- `share_verify()`：校验密码 → `build_share_access_token` 签发 1 小时短时 JWT。
- `share_download()`：校验分享有效 + `office_token` 合法 → `FileResponse`。

### 8.4 `app/api/office.py` — OnlyOffice 编排（tags `office`）

| 端点 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/api/office/status` | GET | 无 | 集成状态（configured/onlyofficeUrl/publicBaseUrl/jwtEnabled） |
| `/api/office/config/{file_id}` | GET | 必须 | 所有者打开配置（可编辑） |
| `/api/office/share/{token}` | GET | share access_token | 访客打开配置（按分享权限） |
| `/onlyoffice/callback` | POST | DS JWT | 保存回调 |

关键函数：

- `_check_onlyoffice_configured()`：未配置返回 503，前端可友好提示。
- `office_config()`：所有者路径，`mode="edit"`，`download_url` 用 `office_base` + `office_token`。
- `office_share_config()`：访客路径，`mode` 由 `share.permission` 决定，依赖 `get_share_from_access_token`。
- `onlyoffice_callback()`：`await handle_callback(db, body)`，始终返回 `{"error": 0/1}`。

### 8.5 系统路由（`app/main.py`）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/health` | GET | 健康检查，返回 `{"status":"ok","app":...}` |
| `/go/{token}` | GET | 旧分享入口重定向到 SPA |
| `/` | GET | 根路径重定向到 `/static/vue/` |
| `/static/*` | StaticFiles | 前端静态资源 |

---

## 9. 服务层

### 9.1 `app/services/auth.py` — 鉴权依赖

| 函数 | 说明 |
|---|---|
| `bearer_scheme` | `HTTPBearer(auto_error=False)`，无凭证不自动报错，便于可选登录 |
| `authenticate_user(db, email, password)` | 邮箱小写查库 + `verify_password`，失败返回 None |
| `_resolve_user(credentials, db)` | 从 Bearer JWT 解析 `sub` → `db.get(User, sub)`，无/无效返回 None |
| `get_current_user(...)` | **必须登录依赖**：无用户 401 |
| `get_optional_user(...)` | **可选登录依赖**：无用户返回 None（下载场景） |

### 9.2 `app/services/storage.py` — 本地文件存储

| 函数 | 说明 |
|---|---|
| `user_dir(user_id)` | 返回/创建 `files_dir/{user_id}` 目录 |
| `build_storage_path(user_id, file_id, ext)` | 路径：`data/files/{user_id}/{file_id}{ext}` |
| `save_upload(user_id, file_id, filename, content)` | 计算扩展名 → 写入字节 |
| `overwrite_document(storage_path, content)` | OnlyOffice 回调用，覆盖原文件 |
| `delete_file(storage_path)` | 删除磁盘文件（存在才删） |
| `file_exists(storage_path)` | `Path.exists()` |

### 9.3 `app/services/share.py` — 分享与令牌

| 函数 | 说明 |
|---|---|
| `create_share(db, user, file_id, permission, password, expires_at)` | 校验所有权 → 建 `Share`（密码哈希可选）→ 提交 |
| `get_share_by_token(db, token)` | 按 token 查分享 |
| `is_share_expired(share)` | `expires_at` 非空且早于 `now_utc()` |
| `check_share_password(share, password)` | 无密码通过；有密码 `verify_password` |
| `build_share_access_token(share)` | 签发 1 小时 JWT（`scope=share`, `share_token`），用于换取 OnlyOffice 配置 |
| `get_share_from_access_token(token, credentials, db)` | **FastAPI 依赖**：校验 access_token scope + share_token 匹配 + 未过期 |
| `build_office_download_token(file_id, share_token=None)` | 签发 15 分钟 JWT（`scope=office_download`），供 DS 无登录下载 |
| `validate_office_download_token(token, file_id, share_token=None)` | 校验 scope/file_id/share_token |

### 9.4 `app/services/onlyoffice.py` — DS 编排

| 函数 | 说明 |
|---|---|
| `document_type_for(ext)` | 扩展名 → `word`/`cell`/`slide`/`pdf` 映射 |
| `office_key(file)` | `{file_id}_{version}`，每次保存后必须变化，DS 据此判断是否重新保存 |
| `parse_office_key(key)` | 从 key 解析 `(file_id, version)` |
| `sign_config(config)` | 开启 JWT 时对整个 config 签名，写入 `config["token"]` |
| `build_document_config(file, mode, user, download_url, callback_url)` | 生成完整打开配置（document/documentType/editorConfig/customization） |
| `verify_callback_token(body)` | 校验回调 body 中的 `token`（未签名时仅调试放行） |
| `handle_callback(db, body)` | **回调核心**：按 status 分发 |

`handle_callback` 的 status 处理逻辑：

| status | 含义 | 处理 |
|---|---|---|
| 1 | 用户连接/断开 | 返回 `{"error":0}`，无操作 |
| 4 | 关闭无修改 | 返回 `{"error":0}` |
| 3 / 7 | 保存出错 | 记录错误日志，返回 `{"error":0}` |
| 2 / 6 | 保存就绪 / 强制保存 | 解析 key → 查文件 → 防旧回调（版本不匹配则忽略）→ httpx 下载新文档 → `overwrite_document` → `version += 1` → 更新 `updated_at`/`file_size` |

---

## 10. 工具层

### 10.1 `app/utils/security.py` — 密码与 JWT

| 函数 | 说明 |
|---|---|
| `now_utc()` | 返回 naive UTC `datetime`（SQLite 存储用） |
| `hash_password(password)` | PBKDF2-HMAC-SHA256，600k 迭代，16 字节盐，格式 `pbkdf2_sha256$iter$salt_hex$hash_hex` |
| `verify_password(password, password_hash)` | 解析格式 → 重算 → `hmac.compare_digest`（常量时间比较，防时序攻击） |
| `create_token(subject, expires_minutes, extra=None)` | 签发 JWT，`sub`/`iat`/`exp` + extra 合并 |
| `decode_token(token)` | 校验签名与过期，失败返回 None |

### 10.2 `app/utils/tokens.py` — 标识生成

| 函数 | 说明 |
|---|---|
| `generate_share_token()` | `secrets.token_urlsafe(16)`，分享短码 |
| `generate_file_id()` | `secrets.token_hex(16)`，users/files/shares 主键 |
| `generate_share_id()` | 同上，分享 ID |

### 10.3 `app/utils/urls.py` — 基地址

双视角基地址，解决 DS 在 Docker 内访问不到 `localhost` 的核心问题。

| 函数 | 说明 |
|---|---|
| `request_base(request)` | **浏览器视角**：取当前请求 Host（分享链接、下载链接跟随实际端口/域名） |
| `office_base(request)` | **DS 视角**：配置了 `PUBLIC_BASE_URL` 时优先（Docker 内 DS 用），否则退化为请求地址 |

---

## 11. OnlyOffice 集成流程

### 11.1 配置生成（对应开发计划 8.3）

`build_document_config` 生成的结构：

```json
{
  "document": {
    "fileType": "docx",
    "key": "{file_id}_{version}",
    "title": "文件名.docx",
    "url": "{base}/api/files/{id}/download?office_token={15min JWT}",
    "permissions": { "edit": true|false, "download": true, "print": true }
  },
  "documentType": "word|cell|slide|pdf",
  "editorConfig": {
    "callbackUrl": "{base}/onlyoffice/callback",
    "mode": "view|edit",
    "lang": "zh-CN",
    "user": { "id": "...", "name": "..." },
    "customization": { "autosave": true, "forcesave": true, ... }
  },
  "token": "{整个 config 的 HS256 签名}"
}
```

### 11.2 回调处理（对应开发计划 8.4）

`/onlyoffice/callback` 流程：

1. `verify_callback_token(body)`：DS 开启 JWT 时校验 `body.token`，未签名仅调试放行
2. 解析 `status`：1/4 无操作；3/7 记录错误；2/6 执行保存
3. `parse_office_key(key)` 解析 `(file_id, version)`
4. 查文件，**版本不匹配则忽略**（防旧回调覆盖新版本）
5. `httpx.AsyncClient` 从 `body.url` 下载最新文档
6. `overwrite_document` 覆盖原文件，`version += 1`，更新时间与大小
7. 返回 `{"error": 0}`（DS 要求格式，否则编辑器报错）

### 11.3 三种令牌体系

| 令牌 | 签发 | 有效期 | 用途 |
|---|---|---|---|
| 登录 JWT | 登录成功 | 1 天 | 浏览器访问所有 `/api/*`（Bearer） |
| 分享 access_token | `/s/{token}/verify` | 1 小时 | 访客换取 OnlyOffice 配置（`scope=share`） |
| office download token | 配置生成时 | 15 分钟 | DS 无登录下载文档（`scope=office_download`） |

---

## 12. 安全模型

### 12.1 密码存储

- PBKDF2-HMAC-SHA256，600,000 次迭代，16 字节随机盐
- 格式 `pbkdf2_sha256$iter$salt_hex$hash_hex`，自包含算法与参数
- `verify_password` 使用 `hmac.compare_digest` 防时序攻击

### 12.2 JWT 密钥管理

- 优先 `JWT_SECRET` 环境变量
- 未设置时自动生成 48 字节 url-safe 密钥并持久化到 `data/.jwt_secret`，保证重启后已签发 token 仍有效
- OnlyOffice JWT 密钥未单独配置时复用应用密钥

### 12.3 访问控制

- **文件隔离**：所有文件操作通过 `_get_owned_file` 校验 `owner_id == user.id`，非所有者 403
- **分享管理**：创建/撤销分享须为文件所有者
- **分享下载**：仅 DS 持有合法 `office_token` 可拉取，杜绝任意下载
- **回调验签**：OnlyOffice 回调校验 JWT 签名，防止伪造保存请求
- **CORS**：默认 `*`，`allow_credentials` 随来源动态调整

### 12.4 时间一致性

- 数据库统一存 naive UTC，`now_utc()` 提供入口
- 响应序列化统一加 `Z` 后缀（`_iso_utc`），避免前端把 naive UTC 当本地时间解析

---

## 13. 前端 SPA

### 13.1 总览

生产 SPA 位于 `app/static/vue/`，单文件 `app.js`（约 1300 行）实现全部页面，使用 Vue 3 + Vue Router（hash 模式）。

```html
<!-- index.html -->
<script src="lib/vue.global.prod.js"></script>
<script src="lib/vue-router.global.prod.js"></script>
<script src="https://code.iconify.design/iconify-icon/2.1.0/iconify-icon.min.js"></script>
```

### 13.2 API 层（`API` 对象）

封装 fetch，自动注入 `Authorization: Bearer`，401 自动清 token 跳登录，204 返回 null，错误解析 `detail`。

### 13.3 全局状态（`store`）

`reactive` 响应式对象：`user` / `files` / `shares` / `currentFolder` / `viewMode` / `loaded`。

### 13.4 路由组件

| 路由 | 组件 | 说明 |
|---|---|---|
| `/` | — | 重定向到 `/dashboard` |
| `/login` | `Login` | 腾讯文档风格双栏登录页 |
| `/register` | `Register` | 注册页，注册成功自动登录 |
| `/dashboard` | `Dashboard` | 三栏布局（Rail+Sidebar+Main），网格/列表视图，上传/分享/删除/收藏 |
| `/viewer` | `Viewer` | OnlyOffice 在线查看/编辑，45s 无就绪提示重试 |
| `/share/:token` | `ShareLanding` | 分享落地页，密码校验 → 打开编辑器 |

### 13.5 路由守卫

`router.beforeEach`：未登录访问 dashboard/viewer 跳 login；已登录访问 login/register 跳 dashboard。

### 13.6 OnlyOffice 编辑器辅助

| 函数 | 说明 |
|---|---|
| `loadScript(src)` | 动态加载 DS 的 `api.js`，失败提示 |
| `createEditor(elId, config, onReady, onError)` | `new DocsAPI.DocEditor`，绑定 `onDocumentReady`/`onError` |
| `fitEditorIframe(offsetTop)` | 撑满 iframe 高度（api.js 会把容器替换为 iframe） |

### 13.7 其他前端资源

- `app/static/svg/`：word/excel/ppt/pdf/txt 文件类型图标

---

## 14. 部署方式

### 14.1 本地开发

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows
pip install -r requirements.txt
cp .env.example .env                # 按需修改
uvicorn app.main:app --reload --port 8000
```

OnlyOffice DS（Docker）：

```bash
docker run -d -p 8080:80 \
  -e JWT_ENABLED=true \
  -e JWT_SECRET=change-me \
  --name onlyoffice --restart unless-stopped \
  onlyoffice/documentserver
```

访问点：
- 前端首页：`http://localhost:8000/`
- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/api/health`

### 14.2 Dockerfile

基于 `python:3.12-slim`，安装依赖 → 复制 `app` → 创建 `data/files` 目录 → 设置 `DATABASE_URL`/`DATA_DIR` 环境变量 → `uvicorn app.main:app --host 0.0.0.0 --port 8000`。

### 14.3 Docker Compose（`docker-compose.yml`）

双容器：

| 服务 | 镜像 | 端口 | 关键环境变量 |
|---|---|---|---|
| `app` | 本地构建 | 8000 | `PUBLIC_BASE_URL=http://host.docker.internal:8000`、`ONLYOFFICE_URL=http://onlyoffice:80`、双 JWT 密钥 |
| `onlyoffice` | `docker.m.daocloud.io/onlyoffice/documentserver` | 8080 | `JWT_ENABLED=true`、`JWT_SECRET` |

数据卷 `./data:/app/data` 持久化数据库与文件。

### 14.4 Nginx 反向代理（`nginx.conf`）

- `location /` → `127.0.0.1:8000`（后端 API + 前端）
- `location /onlyoffice/` → `127.0.0.1:8080`（DS，含 WebSocket 升级）
- `location /onlyoffice/websocket/` → DS WebSocket（协同编辑），`proxy_read_timeout 600s`
- `client_max_body_size 60m`

### 14.5 `PUBLIC_BASE_URL` 注意事项

> OnlyOffice DS 会直接访问 `PUBLIC_BASE_URL` 下载文档、回调保存。DS 在 Docker 容器内时 `localhost` 不可达：
> - Docker Desktop（Win/Mac）：`http://host.docker.internal:8000`
> - Linux 服务器：局域网 IP 或域名
> - 有域名 + Nginx/HTTPS：`https://your-domain.com`

---

## 15. 测试体系

### 15.1 pytest 单元/集成测试（`tests/test_*.py`）

`pytest.ini` 配置 `testpaths = tests`，`conftest.py` 在导入 app 前设置独立临时数据库与环境变量，避免污染开发数据。

| 文件 | 覆盖 |
|---|---|
| `conftest.py` | `client`/`auth_headers` fixture（alice + bob）、`make_docx` 构造最小 docx |
| `test_auth.py` | 健康检查、注册/重复/弱密码、登录/错误密码、me、未登录 401 |
| `test_files.py` | 上传/列表/详情/下载/删除、需鉴权、拒绝坏扩展名、**用户隔离**、收藏持久化 |
| `test_shares.py` | 创建/公开信息、密码保护、有效期、撤销、下载需 office_token、他人不可管理、URL 用请求地址、时间带 Z、DELETE 空 204 |
| `test_office.py` | 所有者配置、分享 view/edit 配置、分享下载、owner 下载、回调保存升级版本、签名 token 回调、错误用例、未配置 503 |

运行：`pytest tests -v`

### 15.2 手动 E2E 脚本（`tests/*.py` 非 test_ 前缀）

需先启动后端（通常 `--port 8010`）与 OnlyOffice DS：

| 文件 | 说明 |
|---|---|
| `e2e_live.py` | httpx 模拟真实用户链路（注册→上传→列表→分享→配置→下载→删除） |
| `e2e_pages.py` | 静态页面与分享落地页可访问性 |
| `spa_flow.py` | Playwright（msedge）SPA 全流程，含根路径重定向、未登录跳转、注册、上传、打开编辑器 |
| `ds_integration.py` | OnlyOffice 真机联调：DS 容器内拉取文档 + 回调可达 |
| `ds_deep.py` | DS 命令服务（`CommandService` info）+ 真实 docx→pdf 转换 |
| `verify_fixes.py` | 三个 bug 修复回归：URL 用请求地址、时间带 Z、DELETE 空 204 |

### 15.3 验收标准（开发计划 §12）

完整业务闭环：注册/登录 → 上传 → 列表 → 在线查看 → 分享 → 他人查看/编辑，须满足：未登录可看分享、只读不可编辑、可编辑保存后重开为最新、密码保护生效、过期自动失效、用户隔离、重启后可用。

---

## 16. 环境变量参考

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///{BASE}/data/app.db` | 数据库连接串，可切 PostgreSQL |
| `DATA_DIR` | `{BASE}/data` | 数据根目录 |
| `JWT_SECRET` | 空（自动生成持久化） | 应用 JWT 密钥 |
| `ONLYOFFICE_URL` | 空 | DS 地址（前端加载 api.js 用），留空表示未部署 |
| `ONLYOFFICE_JWT_ENABLED` | `true` | 是否开启 DS JWT 校验 |
| `ONLYOFFICE_JWT_SECRET` | 空（复用应用密钥） | DS JWT 密钥 |
| `PUBLIC_BASE_URL` | 空（用请求地址） | 应用对外可访问地址，Docker/公网必填 |
| `DEBUG` | `true` | 调试模式（回调未签名时放行等） |

---

## 附录：后续扩展方向（开发计划 §14）

- 将 SQLite 替换为 PostgreSQL
- 将本地存储替换为 MinIO/S3
- 接入 LibreOffice 做 `.doc` 转 `.docx`
- 接入 Pandoc/Mammoth 做 Markdown 格式化
- 增加文档版本历史
- 增加文件预览权限审计
- 增加管理员后台
