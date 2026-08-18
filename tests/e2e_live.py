# -*- coding: utf-8 -*-
"""端到端实测：模拟真实用户操作链路（注册→上传→列表→分享→OnlyOffice 配置→下载→删除）。"""
import io
import sys
import zipfile
import httpx

BASE = "http://127.0.0.1:8010"
client = httpx.Client(base_url=BASE, timeout=30)
ok = 0
fail = 0

def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [PASS] {name}")
    else:
        fail += 1
        print(f"  [FAIL] {name} {extra}")

def make_docx(name="hello"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{name}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()

print("== 1. 注册 / 登录 ==")
r = client.post("/api/auth/register", json={"email": "e2e@example.com", "password": "secret123", "name": "E2E测试员"})
check("注册 201", r.status_code == 201, str(r.status_code))
r = client.post("/api/auth/login", json={"email": "e2e@example.com", "password": "secret123"})
check("登录 200", r.status_code == 200, str(r.status_code))
token = r.json()["access_token"]
h = {"Authorization": f"Bearer {token}"}

r = client.get("/api/auth/me", headers=h)
check("me 200", r.status_code == 200 and r.json()["email"] == "e2e@example.com", str(r.status_code))

print("== 2. 上传 / 列表 / 下载 ==")
files = {"file": ("E2E文档.docx", make_docx("E2E content"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
r = client.post("/api/files/upload", headers=h, files=files)
check("上传 201", r.status_code == 201, str(r.status_code))
f = r.json()
file_id = f["id"]
check("文件版本 v1", f["version"] == 1)

r = client.get("/api/files", headers=h)
check("列表包含文件", any(x["id"] == file_id for x in r.json()))

r = client.get(f"/api/files/{file_id}/download", headers=h)
check("下载 200 且为 zip", r.status_code == 200 and r.content.startswith(b"PK"), str(r.status_code))

print("== 3. 分享（无密码/只读） ==")
r = client.post("/api/shares", headers=h, json={"file_id": file_id, "permission": "view"})
check("创建分享 201", r.status_code == 201, str(r.status_code))
share = r.json()
stoken = share["token"]
check("分享 URL 正确", share["url"] == f"{BASE}/s/{stoken}")

# 未登录访问公开信息
r = client.get(f"/s/{stoken}/info")
check("公开 info valid", r.status_code == 200 and r.json()["valid"] and not r.json()["requires_password"])

r = client.post(f"/s/{stoken}/verify", json={})
check("verify 通过", r.status_code == 200 and r.json()["ok"], str(r.status_code))
access_token = r.json()["access_token"]

print("== 4. OnlyOffice 配置 ==")
r = client.get(f"/api/office/config/{file_id}", headers=h)
check("所有者配置 200", r.status_code == 200, str(r.status_code))
cfg = r.json()["config"]
check("所有者 mode=edit", cfg["editorConfig"]["mode"] == "edit")
check("key 含版本", cfg["document"]["key"] == f"{file_id}_1")
check("回调地址", cfg["editorConfig"]["callbackUrl"].endswith("/onlyoffice/callback"))
check("下载地址带令牌", "office_token=" in cfg["document"]["url"])
check("配置已签名", "token" in cfg)

r = client.get(f"/api/office/share/{stoken}", headers={"Authorization": f"Bearer {access_token}"})
check("分享配置 200", r.status_code == 200, str(r.status_code))
scfg = r.json()["config"]
check("分享 mode=view（只读）", scfg["editorConfig"]["mode"] == "view")

print("== 5. 分享下载令牌 ==")
office_token = scfg["document"]["url"].split("office_token=")[1]
r = client.get(f"/s/{stoken}/download?office_token={office_token}")
check("分享下载 200", r.status_code == 200 and r.content.startswith(b"PK"), str(r.status_code))
r = client.get(f"/s/{stoken}/download")
check("无令牌下载 403", r.status_code == 403, str(r.status_code))

print("== 6. 用户隔离 ==")
client.post("/api/auth/register", json={"email": "e2e-bob@example.com", "password": "secret123"})
r = client.post("/api/auth/login", json={"email": "e2e-bob@example.com", "password": "secret123"})
bob_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
check("他人访问文件 403", client.get(f"/api/files/{file_id}", headers=bob_h).status_code == 403)
check("他人删除文件 403", client.delete(f"/api/files/{file_id}", headers=bob_h).status_code == 403)
check("他人取配置 403", client.get(f"/api/office/config/{file_id}", headers=bob_h).status_code == 403)

print("== 7. 密码保护分享 ==")
r = client.post("/api/shares", headers=h, json={"file_id": file_id, "permission": "edit", "password": "pw123"})
check("创建密码分享 201", r.status_code == 201, str(r.status_code))
pt = r.json()["token"]
check("错误密码 403", client.post(f"/s/{pt}/verify", json={"password": "nope"}).status_code == 403)
r = client.post(f"/s/{pt}/verify", json={"password": "pw123"})
check("正确密码 200", r.status_code == 200, str(r.status_code))
pcfg = client.get(f"/api/office/share/{pt}", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).json()["config"]
check("密码分享 mode=edit", pcfg["editorConfig"]["mode"] == "edit")

print("== 8. 撤销 / 删除 ==")
r = client.delete(f"/api/shares/{share['id']}", headers=h)
check("撤销分享 204", r.status_code == 204, str(r.status_code))
check("撤销后 info invalid", client.get(f"/s/{stoken}/info").json()["valid"] is False)
r = client.delete(f"/api/files/{file_id}", headers=h)
check("删除文件 204", r.status_code == 204, str(r.status_code))
check("删除后列表为空", all(x["id"] != file_id for x in client.get("/api/files", headers=h).json()))

print(f"\n===== 结果: {ok} 通过, {fail} 失败 =====")
sys.exit(1 if fail else 0)
