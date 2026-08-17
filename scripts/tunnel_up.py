"""一键起服务 + 起 Cloudflare Tunnel,并直接打印飞书事件订阅回调地址。

用法:
    python scripts/tunnel_up.py

做的事:
1. 检查 :8000 服务,没起则后台拉起
2. 用 cloudflared 起 Quick Tunnel(免费、无需域名、无需登录)
3. 从 cloudflared 日志解析出 trycloudflare.com 公网 URL
4. 打印「事件订阅回调地址」,复制去飞书后台粘贴即可

cloudflared 位置:优先 D:/d/cloudflared/cloudflared.exe,其次 PATH。
"""
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HOST = "127.0.0.1"
PORT = 8000
HEALTH_URL = f"http://{HOST}:{PORT}/api/health"
WEBHOOK_PATH = "/api/feishu/webhook"
CFL_LOG = BASE / "data" / "cloudflared.log"   # cloudflared 运行日志(含 URL)

DETACH = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
URL_RE = re.compile(r"https://[\w-]+\.trycloudflare\.com")


def http_get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def service_alive():
    body = http_get(HEALTH_URL, timeout=2)
    return bool(body and '"ok":true' in body)


def start_service():
    print(f"[1/3] 本地服务 :{PORT} 未运行,后台拉起 ...", flush=True)
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", HOST, "--port", str(PORT)],
        cwd=str(BASE), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=DETACH)
    for _ in range(30):
        time.sleep(1)
        if service_alive():
            return True
    return False


def cloudflared_bin():
    """找 cloudflared:优先 D:/d/cloudflared,其次 PATH。"""
    p = Path(r"D:/d/cloudflared/cloudflared.exe")
    if p.is_file():
        return str(p)
    return shutil.which("cloudflared")


def url_from_log():
    """从 cloudflared 日志的 JSON 行里找 trycloudflare.com URL(优先仍可访问的)。"""
    if not CFL_LOG.is_file():
        return None
    for line in CFL_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if "trycloudflare.com" not in line:
            continue
        m = URL_RE.search(line)
        if m:
            url = m.group(0)
            # 隧道刚建可能不可达,验证 health 通了才返回
            if http_get(url + "/api/health", timeout=4) and '"ok":true' in (
                    http_get(url + "/api/health", timeout=4) or ""):
                return url
    return None


def start_tunnel():
    print("[2/3] 拉起 cloudflared Quick Tunnel ...", flush=True)
    bin_ = cloudflared_bin()
    if not bin_:
        print("[错误] 找不到 cloudflared。请安装到 D:/d/cloudflared/ 或加入 PATH。", flush=True)
        return None
    CFL_LOG.write_text("", encoding="utf-8")   # 清空旧日志
    subprocess.Popen(
        [bin_, "tunnel", "--url", f"http://{HOST}:{PORT}",
         "--logfile", str(CFL_LOG), "--loglevel", "info", "--no-autoupdate"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=DETACH)
    for _ in range(45):
        time.sleep(1)
        url = url_from_log()
        if url:
            return url
    return None


def main():
    print("=" * 52, flush=True)
    print("  一键启动:本地服务 + Cloudflare Tunnel", flush=True)
    print("=" * 52, flush=True)

    if not service_alive() and not start_service():
        print("[错误] 本地服务启动失败,请先手动跑 python scripts/launcher.py --server", flush=True)
        sys.exit(1)
    print("  ✓ 本地服务运行中", flush=True)

    url = url_from_log()
    if not url:
        url = start_tunnel()
    if not url:
        print("[错误] 拿不到隧道地址。看 data/cloudflared.log 报错;", flush=True)
        print("       常见原因:网络连不上 Cloudflare(需能访问外网)。", flush=True)
        sys.exit(1)

    print("  ✓ 隧道就绪:", url, flush=True)
    print("-" * 52, flush=True)
    print("  事件订阅回调地址(复制去飞书后台粘贴):", flush=True)
    print("", flush=True)
    print(f"      {url}{WEBHOOK_PATH}", flush=True)
    print("", flush=True)
    print("  飞书后台路径:应用「知识库客服」→ 事件与回调 →", flush=True)
    print("  事件订阅 → 请求地址 URL → 粘贴上面地址 → 保存", flush=True)
    print("-" * 52, flush=True)
    print("  提示:隧道在后台运行。想关掉:任务管理器结束 cloudflared.exe。", flush=True)
    print("  注意:Quick Tunnel 每次重启地址会变,以本脚本显示为准。", flush=True)


if __name__ == "__main__":
    main()
