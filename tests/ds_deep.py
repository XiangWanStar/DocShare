# -*- coding: utf-8 -*-
"""DS 深度验证：命令服务 + 真实文档转换（docx->pdf），证明文档管线端到端可用。"""
import io
import json
import sys
import zipfile
import httpx
import jwt as pyjwt

SECRET = "dev-onlyoffice-secret-0123456789abcdef0123456789abcdef"
APP = "http://127.0.0.1:8010"
DS = "http://localhost:8080"
client = httpx.Client(timeout=120)
ok = fail = 0

def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  [PASS]", name)
    else: fail += 1; print("  [FAIL]", name, extra)

print("== 1. 命令服务 info（编辑后端就绪） ==")
body = {"c": "info"}
signed = {"token": pyjwt.encode(body, SECRET, algorithm="HS256")}
r = client.post(DS + "/coauthoring/CommandService.ashx", json=signed)
check("CommandService 200", r.status_code == 200, str(r.status_code) + r.text[:200])
info = r.json()
check("info 返回成功", info.get("error") == 0, str(info)[:200])

print("== 2. 真实转换测试：app 中的 docx -> DS 转换 -> pdf ==")
# 登录 + 上传
appc = httpx.Client(base_url=APP, timeout=60)
appc.post("/api/auth/register", json={"email": "conv@example.com", "password": "secret123"})
lg = appc.post("/api/auth/login", json={"email": "conv@example.com", "password": "secret123"})
h = {"Authorization": f"Bearer {lg.json()['access_token']}"}
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
    z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DocShare conversion test</w:t></w:r></w:p></w:body></w:document>')
up = appc.post("/api/files/upload", headers=h, files={"file": ("转换测试.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
fid = up.json()["id"]

# 取 office 配置中的 document.url（DS 可达：host.docker.internal）
cfg = appc.get(f"/api/office/config/{fid}", headers=h).json()["config"]
doc_url = cfg["document"]["url"]
check("取到文档 URL", doc_url.startswith("http://host.docker.internal:8010/"), doc_url)

# 转换请求（需要 JWT 签名）
conv_body = {
    "url": doc_url,
    "outputtype": "pdf",
    "filetype": "docx",
    "title": "转换测试",
    "key": "conv-test-001",
}
signed_conv = {"token": pyjwt.encode(conv_body, SECRET, algorithm="HS256")}
r = client.post(DS + "/ConvertService.ashx", json=signed_conv)
check("ConvertService 200", r.status_code == 200, str(r.status_code) + r.text[:300])
cj = r.json()
if cj.get("error") == 0 and cj.get("fileUrl"):
    check("转换成功并返回文件", True)
    pdf = client.get(cj["fileUrl"])
    check("PDF 内容以 %PDF 开头", pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), str(pdf.status_code) + pdf.content[:10])
else:
    check("转换成功并返回文件", False, str(cj)[:300])

print(f"\n===== DS 深度验证: {ok} 通过, {fail} 失败 =====")
sys.exit(1 if fail else 0)
