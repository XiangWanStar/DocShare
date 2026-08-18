"""分享短码与文件令牌生成。"""
import secrets


def generate_share_token() -> str:
    """生成分享短码（16 字节 url-safe）。"""
    return secrets.token_urlsafe(16)


def generate_file_id() -> str:
    """生成 UUID（32 位 hex），用于 users/files/shares 主键。"""
    return secrets.token_hex(16)


def generate_share_id() -> str:
    return secrets.token_hex(16)
