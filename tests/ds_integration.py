# -*- coding: utf-8 -*-
"""OnlyOffice 真机联调：DS 配置生成 + DS 容器内拉取文档 + 回调路由可达。"""
import io
import json
import subprocess
import sys
import zipfile
import httpx

BASE = "http://127.0.0.1:8010"
client = httpx.Client(base_url=BASE, timeout=30)
ok = fail = 0

def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  [PASS]", name)
    else: fail += 1; print("  [FAIL]", name, extra)

def make_docx(text="OnlyOffice 联调文档"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()

def docker_exec(cmd):
    return subprocess.run(["docker", "exec", "docshare-onlyoffice", "sh", "-c", cmd],
                          capture_output=True, text=True, timeout=60)

print("== 1. 应用侧配置 ==")
client.post("/api/auth/register", json={"email": "dsint@example.com", "password": "secret123"})
r = client.post("/api/auth/login", json={"email": "dsint@example.com", "password": "secret123"})
h = {"Authorization": f"Bearer {r.json()['access_token']}"}
up = client.post("/api/files/upload", headers=h, files={"file": ("DS联调.docx", make_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
check("上传 201", up.status_code == 201, str(up.status_code))
fid = up.json()["id"]

cfg = client.get(f"/api/office/config/{fid}", headers=h).json()["config"]
doc_url = cfg["document"]["url"]
check("document.url 使用 PUBLIC_BASE_URL(host.docker.internal)", doc_url.startswith("http://host.docker.internal:8010/"), doc_url)
check("document.key 含版本", cfg["document"]["key"] == f"{fid}_1")
check("mode=edit", cfg["editorConfig"]["mode"] == "edit")
check("配置签名 token 存在", "token" in cfg)
check("callbackUrl 指向 host.docker.internal", cfg["editorConfig"]["callbackUrl"].startswith("http://host.docker.internal:8010/onlyoffice/callback"))

print("== 2. 从 DS 容器内部拉取文档（验证 DS→App 连通 + 令牌鉴权） ==")
r1 = docker_exec(f"curl -s -o /tmp/dl.docx -w '%{{http_code}}' '{doc_url}'")
check("DS 内 curl 文档返回 200", r1.stdout.strip() == "200", r1.stdout.strip())
r2 = docker_exec("head -c 2 /tmp/dl.docx | od -An -c | head -1")
check("下载内容为 zip (PK)", "P" in r2.stdout and "K" in r2.stdout, r2.stdout)

# 无令牌应 401/403
no_tok = doc_url.split("?")[0]
r3 = docker_exec(f"curl -s -o /dev/null -w '%{{http_code}}' '{no_tok}'")
check("无令牌下载被拒绝 (401)", r3.stdout.strip() == "401", r3.stdout.strip())

print("== 3. 分享场景：DS 内拉取分享文档 ==")
sh = client.post("/api/shares", headers=h, json={"file_id": fid, "permission": "view"}).json()
vtok = client.post(f"/s/{sh['token']}/verify", json={}).json()["access_token"]
scfg = client.get(f"/api/office/share/{sh['token']}", headers={"Authorization": f"Bearer {vtok}"}).json()["config"]
check("分享配置 mode=view", scfg["editorConfig"]["mode"] == "view")
sdl = scfg["document"]["url"]
r4 = docker_exec(f"curl -s -o /dev/null -w '%{{http_code}}' '{sdl}'")
check("DS 内拉取分享文档 200", r4.stdout.strip() == "200", r4.stdout.strip())

print("== 4. 回调路由可达性 ==")
r5 = docker_exec("curl -s -o /dev/null -w '%{http_code}' -X POST 'http://host.docker.internal:8010/onlyoffice/callback' -H 'Content-Type: application/json' -d '{}'")
# 空 body 会返回 {"error": 1}（JSON 解析失败）而非连接错误 → 200 即路由可达
check("回调路由可达 (200)", r5.stdout.strip() == "200", r5.stdout.strip())

print("== 5. 应用 office 状态 ==")
st = client.get("/api/office/status").json()
check("office 状态 configured=true", st["configured"] is True, str(st))
check("onlyofficeUrl=localhost:8080", st["onlyofficeUrl"] == "http://localhost:8080", st["onlyofficeUrl"])

print(f"\n===== OnlyOffice 真机联调: {ok} 通过, {fail} 失败 =====")
sys.exit(1 if fail else 0)
