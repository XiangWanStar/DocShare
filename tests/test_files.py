"""文件管理测试（M3 验收）：上传 / 列表 / 详情 / 下载 / 删除 / 隔离。"""
from tests.conftest import make_docx


def upload_docx(client, headers, name="测试文档.docx"):
    return client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": (name, make_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )


def test_upload_list_download_delete(client, auth_headers):
    h = auth_headers["alice"]

    # 上传
    up = upload_docx(client, h)
    assert up.status_code == 201
    f = up.json()
    file_id = f["id"]
    assert f["filename"] == "测试文档.docx"
    assert f["version"] == 1
    assert f["file_size"] > 0

    # 列表
    lst = client.get("/api/files", headers=h)
    assert lst.status_code == 200
    assert any(x["id"] == file_id for x in lst.json())

    # 详情
    detail = client.get(f"/api/files/{file_id}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["filename"] == "测试文档.docx"

    # 下载
    dl = client.get(f"/api/files/{file_id}/download", headers=h)
    assert dl.status_code == 200
    assert dl.content.startswith(b"PK")  # zip 文件头

    # 删除
    rm = client.delete(f"/api/files/{file_id}", headers=h)
    assert rm.status_code == 204
    assert client.get(f"/api/files/{file_id}", headers=h).status_code == 404


def test_upload_requires_auth(client):
    assert upload_docx(client, {}).status_code == 401


def test_upload_rejects_bad_extension(client, auth_headers):
    h = auth_headers["alice"]
    resp = client.post(
        "/api/files/upload", headers=h,
        files={"file": ("evil.exe", b"MZ...", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_file_isolation_between_users(client, auth_headers):
    h_alice = auth_headers["alice"]
    h_bob = auth_headers["bob"]

    f = upload_docx(client, h_alice).json()
    file_id = f["id"]

    # bob 不能看、不能下载、不能删除 alice 的文件
    assert client.get(f"/api/files/{file_id}", headers=h_bob).status_code == 403
    assert client.get(f"/api/files/{file_id}/download", headers=h_bob).status_code == 403
    assert client.delete(f"/api/files/{file_id}", headers=h_bob).status_code == 403

    # bob 的列表里没有 alice 的文件
    bob_list = client.get("/api/files", headers=h_bob).json()
    assert all(x["id"] != file_id for x in bob_list)

def test_toggle_star_persisted(client, auth_headers):
    """收藏切换应持久化到数据库。"""
    from app.database import SessionLocal
    from app.models import File

    h = auth_headers["alice"]
    fid = upload_docx(client, h).json()["id"]

    # 收藏
    r1 = client.post(f"/api/files/{fid}/star", headers=h)
    assert r1.status_code == 200
    assert r1.json()["starred"] is True

    # 从数据库直接验证（非内存）
    db = SessionLocal()
    rec = db.get(File, fid)
    assert rec.starred is True
    db.close()

    # 列表带 starred
    lst = client.get("/api/files", headers=h).json()
    assert any(x["id"] == fid and x["starred"] for x in lst)

    # 取消收藏
    r2 = client.post(f"/api/files/{fid}/star", headers=h)
    assert r2.json()["starred"] is False

    # 他人不可收藏
    assert client.post(f"/api/files/{fid}/star", headers=auth_headers["bob"]).status_code == 403
