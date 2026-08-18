"""用户注册 / 登录 / 当前用户测试（M2 验收）。"""
from tests.conftest import make_docx


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_and_login(client):
    resp = client.post("/api/auth/register", json={
        "email": "user1@example.com", "password": "secret123", "name": "张三",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "user1@example.com"
    assert data["name"] == "张三"
    assert "password" not in data

    # 重复注册
    dup = client.post("/api/auth/register", json={
        "email": "USER1@example.com", "password": "secret123",
    })
    assert dup.status_code == 409

    # 弱密码
    weak = client.post("/api/auth/register", json={
        "email": "weak@example.com", "password": "123",
    })
    assert weak.status_code == 422

    # 登录
    login = client.post("/api/auth/login", json={
        "email": "user1@example.com", "password": "secret123",
    })
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert token

    # 错误密码
    bad = client.post("/api/auth/login", json={
        "email": "user1@example.com", "password": "wrong",
    })
    assert bad.status_code == 401

    # 当前用户
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["id"]

    # 未登录访问
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
