# DocShare

> 轻量级文档在线查看 / 编辑 / 分享系统

基于 **FastAPI + SQLite + OnlyOffice Document Server** 的轻量级文档协作平台。支持多格式 Office 文档上传、在线查看与编辑、生成分享链接（只读 / 可编辑 / 密码保护 / 有效期），用户文件互相隔离。前端为单文件 Vue 3 SPA，**零构建步骤**，开箱即用。

## 功能特性

- **用户体系**：注册 / 登录 / JWT 鉴权
- **文档管理**：上传、列表、下载、删除、收藏，支持 `.docx` / `.xlsx` / `.pptx` / `.pdf` / `.txt` 等格式
- **在线编辑**：集成 OnlyOffice，查看 / 编辑一体，保存后自动回写文件并升级版本
- **链接分享**：生成分享链接，支持只读 / 可编辑 / 密码保护 / 有效期，未登录访客可在线查看
- **安全隔离**：按用户分目录存储，密码 PBKDF2 哈希，OnlyOffice 回调验签，下载使用短时签名令牌

## 技术栈

| 模块 | 技术 |
|---|---|
| 后端 | Python 3.11+ / FastAPI |
| ORM | SQLAlchemy 2.0 |
| 数据库 | SQLite（`./data/app.db`，可平滑迁移 PostgreSQL） |
| 存储 | 本地磁盘（`./data/files/{user_id}/`） |
| 鉴权 | PyJWT（HS256） |
| 在线 Office | OnlyOffice Document Server |
| 前端 | Vue 3 SPA（单文件，零构建） |
| 部署 | Docker Compose + Nginx |

## 架构概览

```text
浏览器（Vue 3 SPA /static/vue）
        │  HTTP + Bearer JWT
        ▼
FastAPI 应用（app/main.py）
├─ API 路由层  app/api/   (auth / files / shares / office)
└─ 静态文件挂载 /static、根路径重定向
        │  调用
        ▼
服务层 app/services/
storage（本地文件）/ auth（鉴权依赖）/ share（分享+令牌）/ onlyoffice（配置+回调）
        │
        ├──────────────┐
        ▼              ▼
工具层 app/utils/   OnlyOffice Document Server（渲染/编辑 + 回调保存）
security（密码+JWT）/ tokens（ID 生成）/ urls（双视角基地址）
        │
        ▼
数据 / 存储层：SQLite (data/app.db) + 本地磁盘 (data/files/{user_id}/)
```

- **所有者编辑流**：浏览器请求配置 → DS 用短时令牌拉取文档 → 编辑保存 → DS 回调下载新文档覆盖原文件 → 版本 +1
- **访客查看流**：访客打开 `/s/{token}` → 校验密码/有效期 → 换取短时 access_token → 按分享权限生成只读/可编辑配置

## 快速开始

### 1. 后端

```bash
python -m venv .venv
source .venv/bin/activate        # Windows cmd: .venv\Scripts\activate | PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env            # Windows cmd: copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

启动后访问：

- 前端首页：<http://localhost:8000/>
- API 文档：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/health>

### 2. OnlyOffice Document Server（Docker）

```bash
# 官方镜像
docker run -d -p 8080:80 \
  -e JWT_ENABLED=true \
  -e JWT_SECRET=change-me-to-a-long-random-secret \
  --name onlyoffice --restart unless-stopped \
  onlyoffice/documentserver

# 国内镜像源（Docker Hub 不可达时）
# docker.m.daocloud.io / docker.1ms.run / hub.rat.dev / docker.nju.edu.cn
docker run -d -p 8080:80 \
  -e JWT_ENABLED=true \
  -e JWT_SECRET=change-me-to-a-long-random-secret \
  --name onlyoffice --restart unless-stopped \
  docker.m.daocloud.io/onlyoffice/documentserver
```

> 首次启动需 1~3 分钟初始化。访问 <http://localhost:8080> 出现欢迎页即成功。

然后在 `.env` 中配置：

```env
# 浏览器加载编辑器用的地址（DS 端口已映射到本机 8080）
ONLYOFFICE_URL=http://localhost:8080
ONLYOFFICE_JWT_SECRET=change-me-to-a-long-random-secret
# 应用对外可访问地址：DS 在 Docker 内无法访问 localhost，按系统填写
#   Docker Desktop (Win/Mac): http://host.docker.internal:8000
#   Linux 服务器: 局域网 IP，如 http://192.168.1.100:8000
PUBLIC_BASE_URL=http://host.docker.internal:8000
```

> ⚠️ **重要**：OnlyOffice DS 会直接访问 `PUBLIC_BASE_URL` 下载文档与回调保存。DS 运行在 Docker 容器内时 `localhost` 不可达：
> - Docker Desktop（Win/Mac）：`http://host.docker.internal:8000`
> - Linux 服务器：局域网 IP 或域名，如 `http://192.168.1.100:8000`
> - 已配域名 + Nginx/HTTPS：`https://your-domain.com`

## 一键部署（Docker Compose）

```bash
# 1. 修改 docker-compose.yml 中的 JWT 密钥
# 2. 启动
docker compose up -d --build

# 应用: http://localhost:8000
# OnlyOffice: http://localhost:8080
```

生产环境建议增加 Nginx 反向代理（见 [`nginx.conf`](nginx.conf)）并配置 HTTPS。

## 配置说明

所有配置项可通过环境变量或 `.env` 文件覆盖（参考 [`.env.example`](.env.example)）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/app.db` | 数据库连接串，可切 PostgreSQL |
| `DATA_DIR` | `./data` | 数据根目录 |
| `JWT_SECRET` | 空（自动生成并持久化） | 应用 JWT 密钥 |
| `ONLYOFFICE_URL` | 空 | DS 地址，留空表示未部署 |
| `ONLYOFFICE_JWT_ENABLED` | `true` | 是否开启 DS JWT 校验 |
| `ONLYOFFICE_JWT_SECRET` | 空（复用应用密钥） | DS JWT 密钥 |
| `PUBLIC_BASE_URL` | 空（用请求地址） | 应用对外可访问地址，Docker / 公网必填 |
| `DEBUG` | `true` | 调试模式 |

## API 一览

<details>
<summary>点击展开完整 API 列表</summary>

```text
# 用户
POST   /api/auth/register            注册
POST   /api/auth/login               登录
GET    /api/auth/me                  当前用户

# 文件
POST   /api/files/upload             上传（multipart）
GET    /api/files                    文件列表
GET    /api/files/{file_id}          文件详情
GET    /api/files/{file_id}/download 下载
POST   /api/files/{file_id}/star     收藏 / 取消收藏
DELETE /api/files/{file_id}          删除

# 分享
POST   /api/shares                   创建分享 {file_id, permission, password?, expires_at?}
GET    /api/shares                   我的分享列表
GET    /api/shares/{share_id}        分享详情
DELETE /api/shares/{share_id}        撤销分享
GET    /s/{token}/info               公开信息
POST   /s/{token}/verify             密码校验 → access_token
GET    /s/{token}/download           分享下载（OnlyOffice 令牌）

# OnlyOffice
GET    /api/office/config/{file_id}  所有者打开配置（可编辑）
GET    /api/office/share/{token}     分享打开配置（按权限只读/可编辑）
POST   /onlyoffice/callback          保存回调
GET    /api/office/status            集成状态
```

</details>

完整交互文档见启动后的 <http://localhost:8000/docs>。

## 目录结构

```text
.
├── app/
│   ├── main.py              # FastAPI 入口（lifespan / 路由注册 / 静态挂载）
│   ├── config.py            # 配置（环境变量 / .env）
│   ├── database.py          # SQLAlchemy 引擎 / 会话 / 迁移
│   ├── models.py            # ORM：User / File / Share
│   ├── schemas.py           # Pydantic 模型
│   ├── api/                 # 路由：auth / files / shares / office
│   ├── services/            # 服务：storage / auth / share / onlyoffice
│   ├── utils/               # 工具：security / tokens / urls
│   └── static/              # 前端静态资源
│       ├── vue/             # Vue 3 单文件 SPA（index.html / app.js / styles.css / lib/）
│       └── svg/             # 文件类型图标
├── tests/                   # pytest 测试 + E2E 脚本
├── data/                    # 运行时数据（自动生成，不入库）
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
└── requirements.txt
```

## 测试

```bash
pytest tests -v
```

覆盖：注册 / 登录 / JWT、上传 / 下载 / 删除 / 用户隔离、分享（密码 / 有效期 / 权限 / 撤销）、OnlyOffice 配置生成与保存回调写回。

`tests/` 下另含手动 E2E 脚本（需先启动服务与 DS）：端到端实测、Playwright SPA 流程、OnlyOffice 真机联调与转换验证。

## 安全说明

- 密码使用 PBKDF2-HMAC-SHA256（600k 迭代）哈希存储
- JWT 密钥未配置时自动生成并持久化到 `data/.jwt_secret`，重启后 token 仍有效
- OnlyOffice 回调校验 JWT 签名，防止伪造保存请求
- 分享下载使用 15 分钟有效签名令牌，杜绝任意下载
- 文件操作统一校验所有权，用户间数据隔离

## 文档

- [CODE_WIKI.md](CODE_WIKI.md) — 结构化代码文档（架构 / 模块职责 / 关键函数 / 依赖 / 运行方式）

## 后续扩展

- 将 SQLite 替换为 PostgreSQL
- 将本地存储替换为 MinIO / S3
- 接入 LibreOffice 做 `.doc` 转 `.docx`
- 增加文档版本历史与权限审计
- 增加管理员后台

## License

本项目基于 [MIT License](LICENSE) 开源。
