"""pytest 全局配置：使用独立临时数据库，避免污染开发数据。"""
import os
import tempfile
from pathlib import Path

import pytest

# ---- 在导入 app 之前设置环境变量 ----
_TMP = tempfile.mkdtemp(prefix="docshare_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["DATA_DIR"] = _TMP
os.environ["JWT_SECRET"] = "test-jwt-secret-0123456789abcdef0123456789abcdef"
os.environ["ONLYOFFICE_URL"] = "http://localhost:8080"
os.environ["ONLYOFFICE_JWT_SECRET"] = "test-onlyoffice-secret-0123456789abcdef0123456789abcdef"
os.environ["ONLYOFFICE_JWT_ENABLED"] = "true"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    """注册并登录两个用户，返回 {alice: headers, bob: headers}。"""
    headers = {}
    for name, email in (("alice", "alice@example.com"), ("bob", "bob@example.com")):
        client.post("/api/auth/register", json={
            "email": email, "password": "secret123", "name": name,
        })
        resp = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
        headers[name] = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    return headers


def make_docx(content: bytes = b"hello world") -> bytes:
    """构造一个最小可用的 docx（zip 含 word/document.xml）。"""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{content.decode()}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()