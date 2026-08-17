"""一键启动器。

用法(命令行):
    python scripts/launcher.py --ingest   解析桌面 Excel → corpus/*.jsonl + 违禁词表
    python scripts/launcher.py --index    重建 RAG 索引
    python scripts/launcher.py --server   启动 Web 服务器(:8000)
    python scripts/launcher.py --deps     安装依赖
    python scripts/launcher.py --check    健康检查

不带参数进入交互菜单。
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from app import corpus  # noqa: E402


def cmd_ingest():
    from tools.build_corpus import main as build
    build()


def cmd_index():
    from app.vector import Embedder, build_index
    n, backend = build_index(force=True, embedder=Embedder.default())
    print(f"[index] {n} 条语料已入索引,backend={backend}", flush=True)


def cmd_server(host=None):
    from app.config import get_app_config
    cfg = get_app_config()
    host = host or cfg.get("host") or "127.0.0.1"
    port = int(cfg.get("port") or 8000)
    if host == "0.0.0.0":
        print(f"[server] 已绑定 0.0.0.0:局域网可访问 http://<本机IP>:{port}/ "
              f"(对外需配 api_token)", flush=True)
    else:
        print(f"[server] 打开 http://127.0.0.1:{port}/ 开始问答", flush=True)
    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port)


def cmd_tunnel():
    """cpolar 隧道:给飞书回调一个公网 URL。"""
    from app.config import get_app_config
    cfg = get_app_config()
    port = int(cfg.get("port") or 8000)
    cpolar = cfg.get("cpolar") or "cpolar"
    print(f"[tunnel] 执行 {cpolar} http {port} ...", flush=True)
    print("[tunnel] 启动后记下 Forwarding 里的 https://xxx.r1n.cn 地址,", flush=True)
    print("[tunnel] 填到飞书后台「事件与回调 → 请求地址」: https://xxx/api/feishu/webhook",
          flush=True)
    try:
        subprocess.run([cpolar, "http", str(port)], check=True)
    except FileNotFoundError:
        print("[tunnel] 找不到 cpolar,请先安装并登录(cpolar 官网)", flush=True)


def cmd_deps():
    subprocess.run([sys.executable, "-m", "pip", "install",
                    "-r", str(BASE / "requirements.txt")], check=True)


def cmd_check():
    from app.config import CONFIG_DIR, DATA_DIR
    from app.vector import ensure_index, DB_PATH
    ok = True

    def _chk(name, cond):
        nonlocal ok
        print(f"  [{'OK' if cond else 'MISS'}] {name}", flush=True)
        if not cond:
            ok = False

    print("[check] 健康检查", flush=True)
    try:
        ensure_index()
        _chk(f"索引就绪 ({DB_PATH})", DB_PATH.is_file())
    except Exception as exc:
        print(f"  [ERR] 索引: {exc}", flush=True)
        ok = False
    _chk("违禁词表 banned_keywords.json",
         (CONFIG_DIR / "banned_keywords.json").is_file())
    _chk("embedding 配置", (CONFIG_DIR / "embedding.local.json").is_file())
    _chk("LLM 配置", (CONFIG_DIR / "llm.local.json").is_file())
    try:
        s = corpus.corpus_stats()
        print(f"  [OK] 语料 {s['total']} 条 / {s['files']} 文件", flush=True)
    except Exception as exc:
        print(f"  [ERR] 语料: {exc}", flush=True)
        ok = False
    if ok:
        print("[check] 全部就绪", flush=True)


MENU = [
    ("1) 解析语料(Excel → corpus/*.jsonl + 违禁词表)", cmd_ingest),
    ("2) 重建索引", cmd_index),
    ("3) 启动服务器(:8000)", cmd_server),
    ("4) 启动 cpolar 隧道(飞书回调用)", cmd_tunnel),
    ("5) 安装依赖", cmd_deps),
    ("6) 健康检查", cmd_check),
]


def main():
    args = sys.argv[1:]
    cmds = {"--ingest": cmd_ingest, "--index": cmd_index,
            "--server": cmd_server, "--tunnel": cmd_tunnel,
            "--deps": cmd_deps, "--check": cmd_check,
            "--lan": lambda: cmd_server("0.0.0.0")}
    for a in args:
        if a in cmds:
            cmds[a]()
            return
    while True:
        print("\n" + "=" * 40)
        print("TikTok Shop 运营规则知识库问答 — 启动器")
        print("=" * 40)
        for label, _ in MENU:
            print("  " + label)
        print("  0) 退出")
        pick = input("回车默认 3) 启动服务器: ").strip()
        if pick == "0" or not pick and pick != "":
            if pick == "0":
                break
        if pick == "":
            cmd_server()
            break
        if pick.isdigit() and 1 <= int(pick) <= len(MENU):
            MENU[int(pick) - 1][1]()
        else:
            print("无效选择", flush=True)


if __name__ == "__main__":
    main()
