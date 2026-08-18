"""分享链接测试（M4 验收）：创建/公开访问/密码/有效期/权限/撤销。"""
from datetime import datetime, timedelta, timezone

from tests.conftest import make_docx


def _upload(client, headers):
    resp = client.post(
        "/api/files/upload", headers=headers,
        files={"file": ("共享文档.docx", make_docx(b"shared"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    return resp.json()["id"]


def _create_share(client, headers, file_id, **kwargs):
    body = {"file_id": file_id, "permission": "view"}
    body.update(kwargs)
    return client.post("/api/shares", headers=headers, json=body)


def test_create_share_and_public_info(client, auth_headers):
    h = auth_headers["alice"]
    file_id = _upload(client, h)

    share = _create_share(client, h, file_id).json()
    token = share["token"]
    assert share["permission"] == "view"
    assert share["has_password"] is False
    assert share["url"].endswith("/s/" + token)

    # 公开信息（未登录）
    info = client.get(f"/s/{token}/info").json()
    assert info["valid"] is True
    assert info["filename"] == "共享文档.docx"
    assert info["requires_password"] is False
    assert info["permission"] == "view"


def test_share_password_protection(client, auth_headers):
    h = auth_headers["alice"]
    file_id = _upload(client, h)
    share = _create_share(client, h, file_id, password="abc123").json()
    token = share["token"]

    # 错误密码
    bad = client.post(f"/s/{token}/verify", json={"password": "wrong"})
    assert bad.status_code == 403

    # 正确密码
    ok = client.post(f"/s/{token}/verify", json={"password": "abc123"})
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert ok.json()["access_token"]


def test_share_expiry(client, auth_headers):
    from app.database import SessionLocal
    from app.models import Share

    h = auth_headers["alice"]
    file_id = _upload(client, h)

    # 创建时不允许过去时间
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert _create_share(client, h, file_id, expires_at=past).status_code == 400

    # 创建未来有效期
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    share = _create_share(client, h, file_id, expires_at=future).json()
    token = share["token"]
    assert client.get(f"/s/{token}/info").json()["valid"] is True

    # 直接把过期时间改为过去，模拟时间流逝
    db = SessionLocal()
    rec = db.get(Share, share["id"])
    rec.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    db.commit()
    db.close()

    info = client.get(f"/s/{token}/info").json()
    assert info["valid"] is False and info["expired"] is True
    assert client.post(f"/s/{token}/verify", json={}).status_code == 403


def test_share_list_and_revoke(client, auth_headers):
    h = auth_headers["alice"]
    file_id = _upload(client, h)
    share = _create_share(client, h, file_id).json()

    lst = client.get("/api/shares", headers=h)
    assert lst.status_code == 200
    assert any(s["id"] == share["id"] for s in lst.json())

    # 撤销
    assert client.delete(f"/api/shares/{share['id']}", headers=h).status_code == 204
    assert client.get(f"/s/{share['token']}/info").json()["valid"] is False


def test_share_download_requires_office_token(client, auth_headers):
    h = auth_headers["alice"]
    file_id = _upload(client, h)
    share = _create_share(client, h, file_id).json()
    token = share["token"]

    # 无令牌拒绝
    assert client.get(f"/s/{token}/download").status_code == 403
    # 伪造令牌拒绝
    assert client.get(f"/s/{token}/download?office_token=bad").status_code == 403


def test_share_cannot_be_managed_by_others(client, auth_headers):
    h_alice = auth_headers["alice"]
    h_bob = auth_headers["bob"]
    file_id = _upload(client, h_alice)
    share = _create_share(client, h_alice, file_id).json()

    # bob 不能创建 alice 文件的分享
    assert _create_share(client, h_bob, file_id).status_code == 403
    # bob 不能撤销 alice 的分享
    assert client.delete(f"/api/shares/{share['id']}", headers=h_bob).status_code == 403

# ---- 回归测试：bug 修复 ----

def test_share_url_uses_request_base(client, auth_headers):
    """分享链接应使用请求地址生成，而非硬编码 PUBLIC_BASE_URL。"""
    h = auth_headers["alice"]
    file_id = _upload(client, h)
    share = _create_share(client, h, file_id).json()
    assert share["url"].startswith("http://testserver/s/")
    assert "localhost:8000" not in share["url"]


def test_datetime_serialized_with_z(client, auth_headers):
    """时间字段必须带 Z（UTC 标记），前端才不会被本地时区误解析。"""
    from datetime import datetime as dt, timedelta, timezone

    h = auth_headers["alice"]
    file_id = _upload(client, h)
    future = (dt.now(timezone.utc) + timedelta(hours=2)).isoformat()
    share = _create_share(client, h, file_id, expires_at=future).json()
    assert share["expires_at"].endswith("Z")
    assert share["created_at"].endswith("Z")

    fl = client.get("/api/files", headers=h).json()[0]
    assert fl["created_at"].endswith("Z")
    assert fl["updated_at"].endswith("Z")

    me = client.get("/api/auth/me", headers=h).json()
    assert me["created_at"].endswith("Z")


def test_delete_share_returns_empty_204(client, auth_headers):
    """DELETE 返回 204 无 body，前端不应解析 JSON。"""
    h = auth_headers["alice"]
    file_id = _upload(client, h)
    share = _create_share(client, h, file_id).json()
    resp = client.delete(f"/api/shares/{share['id']}", headers=h)
    assert resp.status_code == 204
    assert resp.content == b""
