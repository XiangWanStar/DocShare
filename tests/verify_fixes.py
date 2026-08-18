# -*- coding: utf-8 -*-
"""验证三个 bug 修复。"""
import io
import sys
import zipfile
from datetime import datetime, timedelta, timezone
import httpx

BASE = "http://127.0.0.1:8010"
client = httpx.Client(base_url=BASE, timeout=30)
ok = fail = 0

def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  [PASS]", name)
    else: fail += 1; print("  [FAIL]", name, extra)

def make_docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()

# 登录（可能已存在，容忍 409）
r = client.post("/api/auth/register", json={"email": "bugfix@example.com", "password": "secret123"})
r = client.post("/api/auth/login", json={"email": "bugfix@example.com", "password": "secret123"})
h = {"Authorization": f"Bearer {r.json()['access_token']}"}

# 上传 + 创建带有效期的分享
fid = client.post("/api/files/upload", headers=h, files={"file": ("修复验证.docx", make_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}).json()["id"]
future = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
r = client.post("/api/shares", headers=h, json={"file_id": fid, "permission": "view", "expires_at": future})
share = r.json()

print("== Fix 1: 分享链接使用请求地址 ==")
check("share url 以请求地址开头", share["url"].startswith(BASE + "/s/"), share["url"])
check("share url 不再指向 localhost:8000", "localhost:8000" not in share["url"], share["url"])
# 用返回的 url 直接访问 info
r = client.get(share["url"].replace(BASE, "") + "/info")
check("用返回链接访问 info 有效", r.status_code == 200 and r.json()["valid"], str(r.status_code) + r.text[:100])

print("== Fix 2: 有效期带 Z 时区标记 ==")
raw = r = client.get(f"/api/shares/{share['id']}", headers=h).json()
check("expires_at 以 Z 结尾", raw["expires_at"].endswith("Z"), str(raw["expires_at"]))
check("created_at 以 Z 结尾", raw["created_at"].endswith("Z"), str(raw["created_at"]))
# 文件列表时间同样带 Z
fl = client.get("/api/files", headers=h).json()[0]
check("文件 created_at 带 Z", fl["created_at"].endswith("Z"), str(fl["created_at"]))
# 前端解析回本地时间应为 5 小时后（UTC+8 时区，实际本地与 UTC 差 8h）
dt = datetime.fromisoformat(raw["expires_at"].replace("Z", "+00:00"))
local = dt.astimezone()
hours_ahead = (local - datetime.now().astimezone()).total_seconds() / 3600
check("有效期距现在约 5 小时（±10 分钟）", 4.8 <= hours_ahead <= 5.2, f"{hours_ahead:.2f}h")

print("== Fix 3: 撤销分享 204 无 body ==")
r = client.delete(f"/api/shares/{share['id']}", headers=h)
check("DELETE 返回 204 且 body 为空", r.status_code == 204 and r.content == b"", f"{r.status_code} body={r.content[:30]!r}")
# 前端 Vue app.js 已处理 204
js = httpx.get(BASE + "/static/vue/app.js").text
check("app.js 处理 204", "if (resp.status === 204) return null;" in js)

print(f"\n===== 修复验证: {ok} 通过, {fail} 失败 =====")
sys.exit(1 if fail else 0)
