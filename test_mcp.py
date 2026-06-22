#!/usr/bin/env python3
"""fudosan-ontology MCP サーバの実テスト。

mcp_server.py を subprocess で起動し、改行区切り JSON-RPC で実ツール呼び出しを行い、
返ってきた実データを検証する。「import できる」だけの自明テストは置かない。
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class MCPClient:
    def __init__(self):
        self.p = subprocess.Popen(
            [sys.executable, str(ROOT / "mcp_server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(ROOT),
        )
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            req["params"] = params
        self.p.stdin.write((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            err = self.p.stderr.read().decode("utf-8", "replace")
            raise AssertionError(f"no response from server; stderr=\n{err}")
        return json.loads(line.decode("utf-8"))

    def tool(self, name, args):
        resp = self.call("tools/call", {"name": name, "arguments": args})
        result = resp["result"]
        payload = json.loads(result["content"][0]["text"])
        return result, payload

    def close(self):
        try:
            self.p.stdin.close()
        except Exception:
            pass
        try:
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


class TestMCP(unittest.TestCase):
    def setUp(self):
        self.c = MCPClient()
        init = self.c.call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "fudosan-ontology")
        self.assertEqual(init["result"]["protocolVersion"], "2024-11-05")

    def tearDown(self):
        self.c.close()

    def test_tools_list(self):
        resp = self.c.call("tools/list")
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertEqual(names, {"resolve_term", "normalize", "assess_risk"})

    def test_resolve_direct(self):
        _, p = self.c.tool("resolve_term", {"term": "ハザードマップ"})
        self.assertTrue(p["matched"])
        self.assertEqual(p["term"], "ハザードマップ")
        self.assertEqual(p["category"], "chousa")

    def test_resolve_alias_paren_reading(self):
        # 括弧付き読み併記の既知語：素トークン『さんため』でも正規形に名寄せ
        _, p = self.c.tool("resolve_term", {"term": "さんため"})
        self.assertTrue(p["matched"])
        self.assertIn("三為", p["term"])

    def test_resolve_unknown_proposes(self):
        _, p = self.c.tool("resolve_term", {"term": "ナゾノゴ"})
        self.assertFalse(p["matched"])
        self.assertIsNone(p["term"])
        self.assertTrue(p["new_term_proposals"])
        for prop in p["new_term_proposals"]:
            self.assertEqual(prop["gate"], "Hold")

    def test_normalize_requirement(self):
        _, p = self.c.tool("normalize", {"kind": "requirement",
                                         "text": "家賃8万以内、2LDK、駅徒歩10分以内、40㎡以上"})
        self.assertEqual(p["kind"], "requirement")
        self.assertTrue(p["requirements"])
        structured = json.loads(p["requirements"][0]["structured"])
        self.assertEqual(structured["rent_max_yen"], 80000)
        self.assertEqual(structured["layout"], "2LDK")
        self.assertEqual(structured["walk_max_min"], 10)

    def test_normalize_address(self):
        _, p = self.c.tool("normalize", {"kind": "address", "text": "千代田区霞が関一丁目２番３号"})
        self.assertEqual(p["addresses"][0]["normalized"], "千代田区霞が関1-2-3")

    def test_normalize_minpaku_needs_confirm(self):
        # 民泊「可」は運用可否を確定せず Approval(要確認) ゲート
        _, p = self.c.tool("normalize", {"kind": "property", "text": "民泊相談可、南向き、築20年"})
        self.assertIn("Approval", p["gates"])
        self.assertTrue(any("民泊" in h for h in p["holds"]))

    def test_normalize_invalid_kind_errors(self):
        result, p = self.c.tool("normalize", {"kind": "foobar", "text": "x"})
        self.assertTrue(result["isError"])
        self.assertEqual(p["status"], "ERROR")

    def test_assess_risk_stub_no_network(self):
        _, p = self.c.tool("assess_risk", {"address": "千代田区霞が関1-2-3"})
        self.assertFalse(p["connected"])
        self.assertIsNone(p["risk_score"])
        self.assertTrue(p["hazard_vocabulary"], "辞書由来の災害/ハザード語彙が空")
        self.assertIn("ハザードマップ", p["hazard_vocabulary"])

    def test_unknown_tool_errors(self):
        result, p = self.c.tool("does_not_exist", {})
        self.assertTrue(result["isError"])
        self.assertIn("未知の tool", p["error"])


if __name__ == "__main__":
    unittest.main()
