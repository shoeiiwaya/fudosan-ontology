"""導入ウィザード（Python / uvx 版）。クライアント選択 → MCP 設定を出力。
ローカル LLM 選択時は搭載メモリを見て推奨モデルを提示する（標準ライブラリのみ）。"""
import json
import os
import shutil
import sys
from datetime import datetime

MCP_SNIPPET = {
    "mcpServers": {
        "fudosan-ontology": {"command": "uvx", "args": ["fudosan-ontology", "serve"]}
    }
}


def _json():
    return json.dumps(MCP_SNIPPET, ensure_ascii=False, indent=2)


def total_ram_gb():
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return None


def recommend_model():
    gb = total_ram_gb()
    if gb is None:
        return {"ram_gb": None, "models": ["Qwen2.5 7B (Q4)", "Llama 3.1 8B (Q4)"],
                "note": "メモリ量を検出できませんでした。一般には 7〜8B 級(Q4)が無難。"}
    if gb < 8:
        t = {"warn": True, "models": ["Llama 3.2 3B (Q4)", "Qwen2.5 3B (Q4)", "Gemma 2 2B"],
             "note": "RAM が少なめ。3〜4B 級の量子化(Q4)を推奨。重いタスクは厳しい。"}
    elif gb < 16:
        t = {"models": ["Qwen2.5 7B (Q4)", "Llama 3.1 8B (Q4)", "Gemma 2 9B (Q4)"], "note": "7〜8B 級(Q4)が快適。"}
    elif gb < 32:
        t = {"models": ["Qwen2.5 14B (Q4)", "Phi-4 14B (Q4)", "Llama 3.1 8B (fp16)"], "note": "13〜14B 級(Q4)まで実用的。"}
    elif gb < 64:
        t = {"models": ["Qwen2.5 32B (Q4)", "Gemma 2 27B (Q4)"], "note": "30B 級(Q4)が狙える。"}
    else:
        t = {"models": ["Llama 3.3 70B (Q4)", "Qwen2.5 72B (Q4)"], "note": "70B 級(Q4)も可。"}
    t["ram_gb"] = gb
    return t


def _local_llm_guide():
    r = recommend_model()
    out = []
    out.append(f"検出した搭載メモリ: {('約 ' + str(r['ram_gb']) + ' GB') if r['ram_gb'] else '不明'}")
    if r.get("warn"):
        out.append("⚠️ メモリに余裕が少なめです。小さめモデル＋量子化を推奨します。")
    out.append("")
    out.append(f"推奨モデル目安: {' / '.join(r['models'])}")
    out.append(f"  {r['note']}")
    out.append("  日本語の不動産文には日本語が強いモデル(Qwen 系 / Sakana 系 / ELYZA 系)が好相性。")
    out.append("  ※ GPU 搭載機は VRAM 基準で。最新の入手可否は各ランナー(Ollama / LM Studio 等)で確認を。")
    out.append("")
    out.append("ローカル LLM ランナー側で本 MCP サーバ(`uvx fudosan-ontology serve`)をツールとして登録すると、")
    out.append("選んだローカルモデルが不動産用語の名寄せを呼べます。設定形式は各ランナーの MCP 対応に従ってください。")
    return "\n".join(out)


def _claude_desktop_path():
    if sys.platform == "darwin":
        return "~/Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform == "win32":
        return "%APPDATA%\\Claude\\claude_desktop_config.json"
    return "~/.config/Claude/claude_desktop_config.json"


CLIENTS = {
    "claude-code": ("Claude Code (CLI)",
                    lambda: "ターミナルで次を実行:\n\n  claude mcp add fudosan-ontology -- uvx fudosan-ontology serve\n"),
    "claude-desktop": ("Claude Desktop",
                       lambda: f"設定ファイル {_claude_desktop_path()} の \"mcpServers\" に追記:\n\n{_json()}"),
    "codex": ("OpenAI Codex CLI",
              lambda: "~/.codex/config.toml に追記:\n\n"
                      "[mcp_servers.fudosan-ontology]\ncommand = \"uvx\"\nargs = [\"fudosan-ontology\", \"serve\"]\n"),
    "cline": ("Cline (VS Code)",
              lambda: "Cline の MCP 設定 (cline_mcp_settings.json) の \"mcpServers\" に追記:\n\n" + _json()),
    "cursor": ("Cursor", lambda: "~/.cursor/mcp.json に追記:\n\n" + _json()),
    "generic": ("その他 / 汎用 MCP クライアント",
                lambda: "MCP 設定の mcpServers に次を追記（多くのクライアントで共通）:\n\n" + _json()),
    "local-llm": ("ローカル LLM で使う（モデル推奨つき）", _local_llm_guide),
}


def client_config_path(client):
    home = os.path.expanduser("~")
    if client == "claude-desktop":
        if sys.platform == "darwin":
            return os.path.join(home, "Library", "Application Support", "Claude", "claude_desktop_config.json")
        if sys.platform == "win32":
            return os.path.join(os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming")), "Claude", "claude_desktop_config.json")
        return os.path.join(home, ".config", "Claude", "claude_desktop_config.json")
    if client == "cursor":
        return os.path.join(home, ".cursor", "mcp.json")
    return None


def merge_mcp_file(file):
    """既存 mcpServers と他キーを保全したままマージ。書き込み前にバックアップ。"""
    cfg, backed = {}, None
    if os.path.exists(file):
        try:
            cfg = json.load(open(file, encoding="utf-8")) or {}
        except Exception:
            cfg = {}
        backed = file + ".bak-" + datetime.now().strftime("%Y%m%dT%H%M%S")
        shutil.copyfile(file, backed)
    else:
        os.makedirs(os.path.dirname(file), exist_ok=True)
    if not isinstance(cfg.get("mcpServers"), dict):
        cfg["mcpServers"] = {}
    cfg["mcpServers"]["fudosan-ontology"] = {"command": "uvx", "args": ["fudosan-ontology", "serve"]}
    with open(file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return file, backed


def install_client(client):
    if client == "claude-code":
        import subprocess
        try:
            r = subprocess.run(["claude", "mcp", "add", "-s", "user", "fudosan-ontology", "--", "uvx", "fudosan-ontology", "serve"])
            if r.returncode == 0:
                sys.stdout.write("✓ Claude Code に登録しました。新しいセッションで有効になります。\n")
                return 0
        except FileNotFoundError:
            pass
        sys.stdout.write("Claude Code CLI が見つかりません。次を実行:\n\n  claude mcp add -s user fudosan-ontology -- uvx fudosan-ontology serve\n")
        return 1
    file = client_config_path(client)
    if file:
        try:
            f, backed = merge_mcp_file(file)
            sys.stdout.write(f"✓ 設定を書き込みました: {f}\n")
            if backed:
                sys.stdout.write(f"  （元の設定は {backed} にバックアップ）\n")
            sys.stdout.write("  クライアントを再起動すると fudosan-ontology が使えます。\n")
            return 0
        except Exception as e:
            sys.stdout.write(f"自動書き込みに失敗: {e}\n")
            return 1
    c = CLIENTS.get(client)
    sys.stdout.write((c[1]() if c else f"不明なクライアント: {client}") + "\n")
    return 0


def print_config(client):
    c = CLIENTS.get(client)
    if not c:
        sys.stdout.write(f"不明なクライアント: {client}\n利用可能: {', '.join(CLIENTS)}\n")
        return 1
    sys.stdout.write(f"\n# {c[0]}\n\n{c[1]()}\n")
    return 0


def help():
    sys.stdout.write(
        "fudosan-ontology — 不動産 業界用語・名寄せオントロジー (MCP)\n\n"
        "使い方:\n"
        "  uvx fudosan-ontology serve     MCP サーバを起動 (クライアントが起動)\n"
        "  uvx fudosan-ontology init      導入ウィザード (クライアントを選んで設定)\n"
        "  uvx fudosan-ontology install <client>  指定クライアントへ設定を自動書き込み\n"
        "  uvx fudosan-ontology config <client>   指定クライアントの設定を表示\n\n"
        "  <client> = " + " | ".join(CLIENTS) + "\n"
    )
    return 0


def run_wizard():
    keys = list(CLIENTS)
    sys.stdout.write("\nfudosan-ontology 導入ウィザード\n使うツールを選んでください:\n\n")
    for i, k in enumerate(keys, 1):
        sys.stdout.write(f"  {i}) {CLIENTS[k][0]}\n")
    sys.stdout.write("\n番号を入力 (Enter で 1): ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    try:
        n = int(line.strip())
        idx = n - 1 if 1 <= n <= len(keys) else 0
    except ValueError:
        idx = 0
    key = keys[idx]
    if key in ("claude-desktop", "cursor", "claude-code"):
        sys.stdout.write(f"\n# {CLIENTS[key][0]}\n設定を自動で書き込みますか？（バックアップを取って追記） (Y/n): ")
        sys.stdout.flush()
        ans = sys.stdin.readline().strip()
        sys.stdout.write("\n")
        if ans[:1].lower() == "n":
            sys.stdout.write(f"{CLIENTS[key][1]()}\n")
        else:
            install_client(key)
    else:
        sys.stdout.write(f"\n# {CLIENTS[key][0]}\n\n{CLIENTS[key][1]()}\n")
    return 0
