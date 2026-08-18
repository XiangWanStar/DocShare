"""请求基地址工具。

- request_base：浏览器视角（分享链接、下载链接），永远取当前请求 Host；
- office_base：OnlyOffice Document Server 视角（文档下载/回调地址），
  配置了 PUBLIC_BASE_URL 时优先（Docker 内 DS 访问不到 localhost），否则退化为请求地址。
"""
from fastapi import Request

from ..config import settings


def request_base(request: Request) -> str:
    """用户可见链接的基地址：取当前请求的 Host（跟随实际端口/域名）。"""
    return str(request.base_url).rstrip("/")


def office_base(request: Request) -> str:
    """OnlyOffice 服务器可访问的基地址。"""
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")
