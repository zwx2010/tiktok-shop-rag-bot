"""一键起服务 + 起 cpolar 隧道,并直接打印飞书事件订阅回调地址。

用法:
    python scripts/tunnel_up.py

做的事:
1. 检查 :8000 服务,没起则后台拉起
2. 检查 cpolar 隧道(转发到 8000),没有则后台拉起
3. 轮询 cpolar 的 inspect 页面(默认 4040)拿到公网 URL
4. 打印「事件订阅回调地址」,复制去飞书后台粘贴即可
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
INSPECT = "http://127.0.0.1:4040/"   # cpolar inspect 页面(内含隧道 JSON)
HEALTH_URL = f"http://{HOST}:{PORT}/api/health"
WEBHOOK_PATH = "/api/feishu/webhook"

DETACH = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP


def http_get(url, timeout=3):
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


def tunnels_from_inspect():
    """从 cpolar inspect 页面解析 (public_https, local_addr) 列表。"""
    html = http_get(INSPECT, timeout=3)
    if not html:
        return []
    m = re.search(r'window\.data = JSON\.parse\("(.*?)"\);', html, re.S)
    if not m:
        return []
    try:
        inner = json.loads('"' + m.group(1) + '"')   # 先解开 JSON 转义字符串
        data = json.loads(inner)                     # 再解析为对象
    except Exception:
        return []
    out = []
    for t in (data.get("UiState") or {}).get("Tunnels") or []:
        url = t.get("PublicUrl") or ""
        addr = t.get("LocalAddr") or ""
        out.append((url, addr))
    return out


def find_feishu_tunnel():
    """找转发到 8000 的隧道,优先 https。"""
    best = None
    for url, addr in tunnels_from_inspect():
        if addr and "8000" in addr:
            if url.startswith("https://"):
                return url, addr
            best = url, addr
    return best or (None, None)


def start_tunnel():
    print("[2/3] cpolar 隧道未就绪,后台拉起(cpolar 会弹个窗口,别关) ...", flush=True)
    cpolar = shutil.which("cpolar") or "cpolar"
    # cpolar 是 TUI 程序,必须给它一个控制台窗口,否则直接崩
    subprocess.Popen(
        [cpolar, "http", str(PORT), "-inspect-addr", "127.0.0.1:4040"],
        cwd=str(BASE), creationflags=subprocess.CREATE_NEW_CONSOLE)
    for _ in range(60):
        time.sleep(1)
        url, _ = find_feishu_tunnel()
        if url:
            return url
    return None


def main():
    print("=" * 52, flush=True)
    print("  一键启动:本地服务 + cpolar 隧道", flush=True)
    print("=" * 52, flush=True)

    if not service_alive() and not start_service():
        print("[错误] 本地服务启动失败,请先手动跑 python scripts/launcher.py --server", flush=True)
        sys.exit(1)
    print("  ✓ 本地服务运行中", flush=True)

    url, _ = find_feishu_tunnel()
    if not url:
        url = start_tunnel()
    if not url:
        print("[错误] 拿不到隧道地址。确认 cpolar 已登录(有 authtoken),或手动跑隧道看报错。", flush=True)
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
    print("  提示:隧道在后台运行。想关掉:任务管理器结束 cpolar.exe。", flush=True)


if __name__ == "__main__":
    main()
