# -*- coding: utf-8 -*-
"""前端 Vue SPA 与分享落地页可访问性验证。"""
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8010", timeout=30)
checks = []

for path in ["/", "/static/vue/", "/static/vue/index.html", "/static/vue/app.js", "/static/vue/styles.css"]:
    r = client.get(path, follow_redirects=False)
    checks.append((path, r.status_code, r.headers.get("content-type", "")))

# 分享落地页（用真实 token）
r0 = client.post("/api/auth/register", json={"email": "page@example.com", "password": "secret123"})
r1 = client.post("/api/auth/login", json={"email": "page@example.com", "password": "secret123"})
h = {"Authorization": f"Bearer {r1.json()['access_token']}"}
import io, zipfile
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("word/document.xml", "<w:document/>")
fup = client.post("/api/files/upload", headers=h, files={"file": ("p.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
sh = client.post("/api/shares", headers=h, json={"file_id": fup.json()["id"]}).json()
r2 = client.get(f"/s/{sh['token']}", follow_redirects=False)
checks.append((f"/s/{sh['token']} 分享落地页", r2.status_code, r2.headers.get("content-type", "")))
r3 = client.get(f"/s/{sh['token']}/info")
checks.append(("分享 info", r3.status_code, r3.json().get("valid")))

allok = True
for path, code, ct in checks:
    okflag = code in (200, 307)
    allok &= okflag
    print(("[PASS] " if okflag else "[FAIL] ") + path + " -> " + str(code) + " " + str(ct)[:40])
print("ALL PASS" if allok else "SOME FAILED")
