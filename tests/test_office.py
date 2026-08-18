"""OnlyOffice 集成测试（M5 验收）：配置生成、分享配置、保存回调写回。"""
import jwt as pyjwt

from app.config import settings
from tests.conftest import make_docx


def _upload(client, headers):
    resp = client.post(
        "/api/files/upload", headers=headers,
        files={"file": ("编辑文档.docx", make_docx(b"v1"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    return resp.json()


def test_office_config_for_owner(client, auth_headers):
    h = auth_headers["alice"]
    f = _upload(client, h)

    resp = client.get(f"/api/office/config/{f['id']}", headers=h)
    assert resp.status_code == 200
    data = resp.json()
    cfg = data["config"]
    assert cfg["documentType"] == "word"
    assert cfg["document"]["fileType"] == "docx"
    assert cfg["document"]["title"] == "编辑文档.docx"
    assert cfg["document"]["key"] == f"{f['id']}_1"
    assert cfg["editorConfig"]["mode"] == "edit"
    assert cfg["editorConfig"]["callbackUrl"].endswith("/onlyoffice/callback")
    assert cfg["editorConfig"]["user"]["name"] == "alice"
    assert cfg["document"]["url"].startswith("http://testserver/api/files/")
    assert "office_token=" in cfg["document"]["url"]

    # 配置签名 token 可解析，payload 与配置一致
    payload = pyjwt.decode(cfg["token"], settings.get_onlyoffice_jwt_secret(), algorithms=["HS256"])
    assert payload["document"]["key"] == cfg["document"]["key"]

    # 他人不可取配置
    assert client.get(f"/api/office/config/{f['id']}", headers=auth_headers["bob"]).status_code == 403


def test_share_office_config_view_and_edit(client, auth_headers):
    h = auth_headers["alice"]
    f = _upload(client, h)

    # 只读分享
    view_share = client.post("/api/shares", headers=h, json={"file_id": f["id"], "permission": "view"}).json()
    vt = view_share["token"]
    vtok = client.post(f"/s/{vt}/verify", json={}).json()["access_token"]
    cfg = client.get(f"/api/office/share/{vt}", headers={"Authorization": f"Bearer {vtok}"}).json()["config"]
    assert cfg["editorConfig"]["mode"] == "view"
    assert cfg["document"]["permissions"]["edit"] is False
    assert cfg["document"]["url"].startswith(f"http://testserver/s/{vt}/download")

    # 可编辑分享
    edit_share = client.post("/api/shares", headers=h, json={"file_id": f["id"], "permission": "edit"}).json()
    et = edit_share["token"]
    etok = client.post(f"/s/{et}/verify", json={}).json()["access_token"]
    cfg2 = client.get(f"/api/office/share/{et}", headers={"Authorization": f"Bearer {etok}"}).json()["config"]
    assert cfg2["editorConfig"]["mode"] == "edit"

    # 无访问令牌拒绝
    assert client.get(f"/api/office/share/{vt}").status_code == 403
    assert client.get(f"/api/office/share/{vt}", headers={"Authorization": "Bearer bad"}).status_code == 403


def test_share_download_with_office_token(client, auth_headers):
    h = auth_headers["alice"]
    f = _upload(client, h)
    share = client.post("/api/shares", headers=h, json={"file_id": f["id"], "permission": "view"}).json()
    token = share["token"]
    vtok = client.post(f"/s/{token}/verify", json={}).json()["access_token"]

    cfg = client.get(f"/api/office/share/{token}", headers={"Authorization": f"Bearer {vtok}"}).json()["config"]
    office_token = cfg["document"]["url"].split("office_token=")[1]
    dl = client.get(f"/s/{token}/download?office_token={office_token}")
    assert dl.status_code == 200
    assert dl.content.startswith(b"PK")


def test_owner_file_download_with_office_token(client, auth_headers):
    h = auth_headers["alice"]
    f = _upload(client, h)
    cfg = client.get(f"/api/office/config/{f['id']}", headers=h).json()["config"]
    office_token = cfg["document"]["url"].split("office_token=")[1]

    # 无需登录，仅凭 office_token 可下载（OnlyOffice 服务器行为）
    dl = client.get(f"/api/files/{f['id']}/download?office_token={office_token}")
    assert dl.status_code == 200


def test_callback_saves_and_bumps_version(client, auth_headers, monkeypatch):
    from app.services import onlyoffice as oo

    h = auth_headers["alice"]
    f = _upload(client, h)
    file_id = f["id"]

    # 模拟 OnlyOffice 服务器返回的新文档内容
    class FakeResponse:
        content = b"PK-new-content-v2"
        def raise_for_status(self): pass

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url): return FakeResponse()

    monkeypatch.setattr(oo.httpx, "AsyncClient", FakeClient)

    # status=4 不保存
    r4 = client.post("/onlyoffice/callback", json={"status": 4, "key": f"{file_id}_1"})
    assert r4.status_code == 200 and r4.json() == {"error": 0}

    # status=2 保存并升级版本
    body = {"status": 2, "key": f"{file_id}_1", "url": "http://ds/download.docx", "users": ["1"]}
    r2 = client.post("/onlyoffice/callback", json=body)
    assert r2.status_code == 200 and r2.json() == {"error": 0}

    detail = client.get(f"/api/files/{file_id}", headers=h).json()
    assert detail["version"] == 2

    # 下载验证内容已更新
    dl = client.get(f"/api/files/{file_id}/download", headers=h)
    assert dl.content == b"PK-new-content-v2"

    # 过期回调（版本不匹配）不覆盖
    r_stale = client.post("/onlyoffice/callback", json={"status": 2, "key": f"{file_id}_1", "url": "http://ds/old.docx"})
    assert r_stale.json() == {"error": 0}
    detail2 = client.get(f"/api/files/{file_id}", headers=h).json()
    assert detail2["version"] == 2


def test_callback_with_signed_token(client, auth_headers, monkeypatch):
    from app.services import onlyoffice as oo

    h = auth_headers["alice"]
    f = _upload(client, h)
    file_id = f["id"]

    class FakeClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def get(self, url):
            class R:
                content = b"PK-signed-v3"
                def raise_for_status(self): pass
            return R()

    monkeypatch.setattr(oo.httpx, "AsyncClient", FakeClient)

    body = {"status": 2, "key": f"{file_id}_1", "url": "http://ds/signed.docx"}
    signed = {"token": pyjwt.encode(body, settings.get_onlyoffice_jwt_secret(), algorithm="HS256")}
    r = client.post("/onlyoffice/callback", json=signed)
    assert r.status_code == 200 and r.json() == {"error": 0}
    assert client.get(f"/api/files/{file_id}", headers=h).json()["version"] == 2


def test_callback_error_cases(client, auth_headers, monkeypatch):
    from app.services import onlyoffice as oo

    h = auth_headers["alice"]
    f = _upload(client, h)
    file_id = f["id"]

    # 不存在的文件
    r = client.post("/onlyoffice/callback", json={"status": 2, "key": "nosuchfile_1", "url": "http://x"})
    assert r.json() == {"error": 1}

    # status=3 记录错误但返回 0
    r3 = client.post("/onlyoffice/callback", json={"status": 3, "key": f"{file_id}_1"})
    assert r3.json() == {"error": 0}

def test_office_config_503_when_not_configured(client, auth_headers, monkeypatch):
    """OnlyOffice 未配置时返回 503，前端可提示而非崩溃。"""
    from app.config import settings

    monkeypatch.setattr(settings, "onlyoffice_url", "")
    h = auth_headers["alice"]
    file_id = _upload(client, h)["id"]
    resp = client.get(f"/api/office/config/{file_id}", headers=h)
    assert resp.status_code == 503
    assert "OnlyOffice" in resp.json()["detail"]

    # 分享配置同样 503
    share = client.post("/api/shares", headers=h, json={"file_id": file_id, "permission": "view"}).json()
    tok = client.post(f"/s/{share['token']}/verify", json={}).json()["access_token"]
    resp2 = client.get(f"/api/office/share/{share['token']}", headers={"Authorization": f"Bearer {tok}"})
    assert resp2.status_code == 503
