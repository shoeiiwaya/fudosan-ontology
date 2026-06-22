#!/usr/bin/env python3
"""fudosan-ontology MCP server — 名寄せ辞書を MCP ツールとして露出する。

理ツール標準を厳守:
  - Python 標準ライブラリのみ。外部パッケージ・ネットワーク呼出なし（全ローカル）。
  - 法令・可否・金額を確定しない（不確実は要確認 / null）。

stdio transport は MCP 標準の「改行区切り JSON」（1 メッセージ 1 行・埋め込み改行なし）。
LSP 式の Content-Length 枠も後方互換で受理する。

tools:
  - resolve_term : 業者用語/表記ゆれ/略語 → 正規形 + 定義 + カテゴリ + 同義語 + 英訳 + 法令出典
  - normalize    : 自由文(住所/希望条件/物件/広告/用語) → 標準タグ・正規化値（ハーネスと同一ロジック）
  - assess_risk  : 住所 → 正規化 + 災害/ハザード語彙（外部リスク評価API接続はスタブ・ネット呼出なし）
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import ontology as O  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "fudosan-ontology", "version": "1.0.0"}

# 災害/ハザード語彙の判定キーワード（chousa ドメイン中心に分布）。
HAZARD_KEYWORDS = (
    "ハザード", "浸水", "洪水", "土砂", "液状化", "津波", "地震", "高潮",
    "内水", "河川", "災害", "防災", "警戒区域", "レッドゾーン", "イエローゾーン",
)

_ONTO = None


def _onto():
    global _ONTO
    if _ONTO is None:
        _ONTO = O.load_ontology()
    return _ONTO


# ====================================================================
# tools
# ====================================================================
def tool_resolve_term(args):
    term = str(args.get("term") or args.get("text") or "").strip()
    if not term:
        raise ValueError("term が必要です")
    onto = _onto()
    matched = onto["alias_to_term"].get(O.norm_key(term))
    if matched:
        e = onto["term_to_entry"].get(matched, {})
        return {
            "tool": "resolve_term",
            "input": term,
            "matched": True,
            "term": matched,
            "reading": e.get("reading", ""),
            "category": e.get("category", ""),
            "synonyms": e.get("synonyms", []),
            "definition_pro": e.get("definition_pro", ""),
            "definition_plain": e.get("definition_plain", ""),
            "english": e.get("english", ""),
            "legal_source": e.get("legal_source"),
            "related_terms": e.get("related_terms", []),
            "caution": e.get("caution"),
        }
    # 辞書未収録 → 新語提案（追加可否は人間判断＝Hold）
    proposals = O.propose_new_terms(term, onto["alias_to_term"], onto.get("known_surfaces"))
    return {
        "tool": "resolve_term",
        "input": term,
        "matched": False,
        "term": None,
        "note": "辞書未収録。新語提案として人間判断(Hold)に回します。",
        "new_term_proposals": proposals,
    }


def tool_normalize(args):
    kind = str(args.get("kind") or "").strip()
    text = str(args.get("text") or "").strip()
    if kind not in O.KINDS:
        raise ValueError(f"kind は {sorted(O.KINDS)} のいずれかです")
    if not text:
        raise ValueError("text が必要です")
    onto = _onto()
    state = O.process([{"row_id": "MCP-001", "kind": kind, "text": text, "memo": ""}], onto)
    return {
        "tool": "normalize",
        "kind": kind,
        "input": text,
        "addresses": state["addresses"],
        "requirements": state["requirements"],
        "conditions": state["conditions"],
        "attrs": state["attrs"],
        "new_term_proposals": state["proposals"],
        "holds": state["holds"],
        "gates": [a["gate_status"] for a in state["audit"]],
    }


def _hazard_vocabulary(onto):
    """辞書から災害/ハザード関連語を抽出する（外部リスク語彙との突き合わせ用）。"""
    terms = []
    for e in onto["entries"]:
        blob = " ".join([
            str(e.get("term", "")),
            str(e.get("definition_pro", "")),
            str(e.get("definition_plain", "")),
            " ".join(e.get("synonyms", []) or []),
        ])
        if any(kw in blob for kw in HAZARD_KEYWORDS):
            terms.append(e["term"])
    return sorted(set(terms))


def tool_assess_risk(args):
    """住所 → 正規化 + 辞書由来の災害/ハザード語彙。

    実リスクスコアの取得は行わない（理ツール標準: ネットワーク呼出なし）。
    外部リスク評価APIへの橋渡しは別レイヤーの責務（docs/RISK_BRIDGE.md）。
    """
    address = str(args.get("address") or args.get("text") or "").strip()
    if not address:
        raise ValueError("address が必要です")
    onto = _onto()
    normalized, notes = O.normalize_address(address)
    return {
        "tool": "assess_risk",
        "input": address,
        "normalized_address": normalized,
        "normalize_notes": notes,
        "risk_score": None,
        "connected": False,
        "note": (
            "リスクスコア接続スタブ。本 OSS はネットワーク呼出を行いません（理ツール標準）。"
            "外部リスク評価 API への接続は別レイヤーで実装します（docs/RISK_BRIDGE.md 参照）。"
        ),
        "hazard_vocabulary": _hazard_vocabulary(onto),
    }


TOOL_HANDLERS = {
    "resolve_term": tool_resolve_term,
    "normalize": tool_normalize,
    "assess_risk": tool_assess_risk,
}


def tool_specs():
    kinds = sorted(O.KINDS)
    return [
        {
            "name": "resolve_term",
            "description": "不動産の業界用語・表記ゆれ・略語を正規形へ名寄せし、定義・カテゴリ・同義語・英訳・法令出典を返す。",
            "inputSchema": {
                "type": "object",
                "properties": {"term": {"type": "string", "description": "名寄せしたい用語・表記ゆれ・略語"}},
                "required": ["term"],
                "additionalProperties": False,
            },
        },
        {
            "name": "normalize",
            "description": "現場の自由文（住所/希望条件/物件文/広告文/用語）を標準タグ・正規化値に落とす。ハーネスと同一ロジック。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": kinds, "description": "入力種別"},
                    "text": {"type": "string", "description": "自由文"},
                },
                "required": ["kind", "text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "assess_risk",
            "description": "住所を正規化し、辞書由来の災害/ハザード語彙を返す。実リスクスコア取得は行わない（接続スタブ）。",
            "inputSchema": {
                "type": "object",
                "properties": {"address": {"type": "string", "description": "住所"}},
                "required": ["address"],
                "additionalProperties": False,
            },
        },
    ]


# ====================================================================
# JSON-RPC / stdio transport
# ====================================================================
def _content_result(payload, is_error=False):
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)}],
        "isError": is_error,
    }


def handle_request(msg):
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method and method.startswith("notifications/"):
        return None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "fudosan-ontology 名寄せ辞書 MCP。resolve_term/normalize/assess_risk。"
                    "全ローカル・ネットワーク呼出なし。法令・可否・金額は確定しない。"
                ),
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": tool_specs()}
        elif method == "tools/call":
            name = params.get("name")
            args = params.get("arguments") or {}
            if name not in TOOL_HANDLERS:
                result = _content_result({"error": f"未知の tool: {name}"}, is_error=True)
            else:
                try:
                    result = _content_result(TOOL_HANDLERS[name](args))
                except Exception as exc:  # tool error は正直に返す（traceback を stdout に出さない）
                    result = _content_result({
                        "status": "ERROR",
                        "tool": name,
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                    }, is_error=True)
        else:
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": str(exc)}}


def read_message(stdin):
    while True:
        first = stdin.readline()
        if first == b"":
            return None
        if first.strip():
            break
    stripped = first.strip()
    if stripped.startswith(b"{"):
        return json.loads(stripped.decode("utf-8"))

    # LSP 式 Content-Length 枠（後方互換）
    headers = {}
    line = first
    while line.strip():
        try:
            key, value = line.decode("ascii").split(":", 1)
            headers[key.lower().strip()] = value.strip()
        except ValueError:
            pass
        line = stdin.readline()
        if line == b"":
            return None
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = stdin.read(length)
    return json.loads(body.decode("utf-8"))


def write_message(stdout, msg):
    body = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stdout.write(body + b"\n")
    stdout.flush()


def serve():
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        msg = read_message(stdin)
        if msg is None:
            return 0
        response = handle_request(msg)
        if response is not None:
            write_message(stdout, response)


if __name__ == "__main__":
    try:
        raise SystemExit(serve())
    except KeyboardInterrupt:
        raise SystemExit(0)
