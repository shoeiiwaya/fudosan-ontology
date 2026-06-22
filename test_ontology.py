#!/usr/bin/env python3
"""fudosan-ontology ハーネスの実テスト。

各 capability（MT-006/033/068/301/302/305）について現実的入力で
出力列・タグ値・正規化値・ゲート発火を検証する。自明な assert True は置かない。
"""
import json
import tempfile
import unittest
from pathlib import Path

import ontology as O


class TestAddressNormalize(unittest.TestCase):  # MT-301
    def test_zenkaku_kanji_chome(self):
        n, notes = O.normalize_address("東京都千代田区霞が関一丁目２番３号")
        self.assertEqual(n, "東京都千代田区霞が関1-2-3")
        self.assertTrue(notes)

    def test_banchi_no(self):
        n, _ = O.normalize_address("大阪府大阪市北区梅田３丁目１番地の２")
        self.assertEqual(n, "大阪府大阪市北区梅田3-1-2")

    def test_kanji_with_unit(self):
        n, _ = O.normalize_address("中央区銀座二十三丁目五番")
        self.assertEqual(n, "中央区銀座23-5")

    def test_dash_unify(self):
        n, _ = O.normalize_address("港区南青山１ー２ー３")
        self.assertEqual(n, "港区南青山1-2-3")

    def test_idempotent_already_normalized(self):
        n, _ = O.normalize_address("港区南青山1-2-3")
        self.assertEqual(n, "港区南青山1-2-3")


class TestAddressClassify(unittest.TestCase):  # MT-302
    def test_jukyo_full(self):
        t, c, g, _ = O.classify_address_type("a", "千代田区霞が関1丁目2番3号")
        self.assertEqual(t, "住居表示")
        self.assertEqual(c, "high")
        self.assertEqual(g, "OK")

    def test_chome_with_banchi_is_jukyo(self):
        # 丁目+番地（都市部）は地番に誤判別しない
        t, _, _, _ = O.classify_address_type("梅田3-1-2", "梅田3丁目1番地の2")
        self.assertEqual(t, "住居表示")

    def test_chiban_aza(self):
        t, c, _, _ = O.classify_address_type("x", "○○市大字田中字山1234番地2")
        self.assertEqual(t, "地番")
        self.assertEqual(c, "high")

    def test_chiban_banchi_only(self):
        t, _, _, _ = O.classify_address_type("田中1234-2", "田中1234番地2")
        self.assertEqual(t, "地番")

    def test_ambiguous_gate_approval(self):
        t, _, g, _ = O.classify_address_type("町名1-2", "町名1-2")
        self.assertEqual(t, "不明")
        self.assertEqual(g, "Approval")


class TestRequirementTags(unittest.TestCase):  # MT-006
    def test_rent_layout_walk_area(self):
        r = O.tag_requirements("家賃8万以内、2LDK、駅徒歩10分以内、40㎡以上")
        self.assertEqual(r["structured"]["rent_max_yen"], 80000)
        self.assertEqual(r["structured"]["layout"], "2LDK")
        self.assertEqual(r["structured"]["walk_max_min"], 10)
        self.assertEqual(r["structured"]["area_min_raw"], "40㎡")

    def test_facility_tags(self):
        r = O.tag_requirements("バス・トイレ別 オートロック 宅配ボックス ペット相談可 南向き 独立洗面台")
        for t in ("バス・トイレ別", "オートロック", "宅配ボックス", "ペット可", "南向き", "独立洗面台"):
            self.assertIn(t, r["tags"])

    def test_area_tags(self):
        r = O.tag_requirements("新宿区か中野区、中央線沿線で")
        self.assertTrue(any(t == "エリア:新宿区" for t in r["tags"]))
        self.assertTrue(any(t == "エリア:中野区" for t in r["tags"]))
        self.assertTrue(any("中央線" in t for t in r["tags"]))


class TestConditionTags(unittest.TestCase):  # MT-033
    def test_pet_ok_vs_ng(self):
        self.assertIn("ペット可", O.tag_conditions("ペット相談可")["tags"])
        self.assertIn("ペット不可", O.tag_conditions("ペット不可")["tags"])

    def test_gakki(self):
        self.assertIn("楽器不可", O.tag_conditions("楽器不可、防音なし")["tags"])

    def test_minpaku_needs_confirm(self):
        c = O.tag_conditions("民泊相談可")
        self.assertIn("民泊可（要確認）", c["tags"])
        self.assertTrue(c["needs_confirm"], "民泊可は運用可否を確定しないこと")

    def test_minpaku_ng_no_confirm(self):
        c = O.tag_conditions("民泊禁止")
        self.assertIn("民泊不可", c["tags"])
        self.assertFalse(c["needs_confirm"])

    def test_soho(self):
        self.assertIn("事務所利用可", O.tag_conditions("SOHO可")["tags"])

    def test_ng_overrides_ok(self):
        # 「ペット不可」を含む文では可語彙があっても不可を優先
        c = O.tag_conditions("ペット不可（相談に応じません）")
        self.assertIn("ペット不可", c["tags"])
        self.assertNotIn("ペット可", c["tags"])


class TestNormalizeAttrs(unittest.TestCase):  # MT-068
    def test_tsubo_to_sqm(self):
        a = O.normalize_attrs("25坪", this_year=2026)["attrs"]
        self.assertAlmostEqual(a["area_sqm"], round(25 * O.TSUBO_TO_SQM, 2), places=2)

    def test_jo_to_sqm(self):
        a = O.normalize_attrs("12帖", this_year=2026)["attrs"]
        self.assertAlmostEqual(a["area_sqm"], round(12 * O.JO_SQM, 2), places=2)

    def test_wareki_to_seireki(self):
        a = O.normalize_attrs("平成2年築", this_year=2026)["attrs"]
        self.assertEqual(a["built_year"], 1990)
        self.assertEqual(a["building_age"], 36)

    def test_reiwa(self):
        a = O.normalize_attrs("令和元年築", this_year=2026)["attrs"]
        self.assertEqual(a["built_year"], 2019)

    def test_chiku_years(self):
        a = O.normalize_attrs("築15年", this_year=2026)["attrs"]
        self.assertEqual(a["building_age"], 15)
        self.assertEqual(a["built_year"], 2011)

    def test_direction_compound_not_misread(self):
        # 「東南向き」を「南」と誤認しない（複合方位優先）
        self.assertEqual(O.normalize_attrs("東南向き")["attrs"]["direction"], "南東")
        self.assertEqual(O.normalize_attrs("北西向き")["attrs"]["direction"], "北西")

    def test_direction_single(self):
        self.assertEqual(O.normalize_attrs("南向きのリビング")["attrs"]["direction"], "南")

    def test_direction_placename_not_misread(self):
        # MT-068 バグ修正: 地名の方位字を方位と誤検出しない（向き/採光等の文脈が無い）
        for txt in ("東口徒歩5分の好立地", "西新宿の物件", "北区の戸建て",
                    "南阿佐ヶ谷駅徒歩3分", "東京都港区の物件です"):
            self.assertIsNone(
                O.normalize_attrs(txt)["attrs"].get("direction"),
                f"地名の方位字を誤検出: {txt}")

    def test_direction_label_and_context_noun(self):
        # 「採光：南」「方角=北西」「バルコニーは南東」など文脈付きは採用する
        self.assertEqual(O.normalize_attrs("採光：南")["attrs"]["direction"], "南")
        self.assertEqual(O.normalize_attrs("方角=北西")["attrs"]["direction"], "北西")
        self.assertEqual(O.normalize_attrs("バルコニーは南東")["attrs"]["direction"], "南東")
        self.assertEqual(O.normalize_attrs("南面・日当たり良好")["attrs"]["direction"], "南")

    def test_direction_mixed_with_placename(self):
        # 文脈付き方位は採用しつつ、同じ文中の地名方位字は無視する
        self.assertEqual(
            O.normalize_attrs("東向きバルコニー、東口徒歩5分")["attrs"]["direction"], "東")
        self.assertEqual(
            O.normalize_attrs("主開口部が南、東京駅徒歩8分")["attrs"]["direction"], "南")


class TestNewTermProposal(unittest.TestCase):  # MT-305
    def setUp(self):
        self.onto = O.load_ontology()

    def test_known_terms_excluded(self):
        props = O.propose_new_terms("マイソクとレインズの確認", self.onto["alias_to_term"])
        cands = [p["candidate"] for p in props]
        self.assertNotIn("マイソク", cands)
        self.assertNotIn("レインズ", cands)

    def test_unknown_proposed_with_hold(self):
        props = O.propose_new_terms(
            "ナゾノゴをフガフガする", self.onto["alias_to_term"], self.onto["known_surfaces"])
        self.assertTrue(props)
        for p in props:
            self.assertEqual(p["gate"], "Hold")
        self.assertTrue(any(c in [p["candidate"] for p in props] for c in ("ナゾノゴ", "フガフガ")))

    def test_paren_reading_term_not_proposed(self):
        # MT-068/305 バグ修正: 括弧付き読み併記の既知語『三為（さんため）』は
        # 素トークン『三為』でも既知語として除外され、新語誤提案されない
        ks = self.onto["known_surfaces"]
        for txt in ("三為で取得した物件", "本物件は三為（さんため）契約です"):
            cands = [p["candidate"] for p in
                     O.propose_new_terms(txt, self.onto["alias_to_term"], ks)]
            self.assertNotIn("三為", cands, f"括弧付き読み併記の既知語が誤提案: {txt} -> {cands}")

    def test_common_words_not_overproposed(self):
        # MT-305 バグ修正: 常用語・既知複合語の素片は新語に上げない
        ks = self.onto["known_surfaces"]
        cands = [p["candidate"] for p in O.propose_new_terms(
            "特約を確認し、業者へ連絡。契約を締結する段取りです。",
            self.onto["alias_to_term"], ks)]
        for w in ("特約", "業者", "連絡", "契約", "段取", "確認"):
            self.assertNotIn(w, cands, f"常用語/素片が誤提案: {w} in {cands}")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.onto = O.load_ontology()

    def test_gates_fire_and_address_masked(self):
        rows = [
            {"row_id": "R-001", "kind": "address", "text": "千代田区霞が関一丁目2番3号"},
            {"row_id": "R-002", "kind": "address", "text": "さくら町2-3"},
            {"row_id": "R-003", "kind": "requirement", "text": "1LDK 家賃10万 ペット可"},
            {"row_id": "R-004", "kind": "property", "text": "民泊相談可、南向き、築20年"},
            {"row_id": "R-005", "kind": "term", "text": "ナゾノゴ という用語"},
        ]
        state = O.process(rows, self.onto)
        gates = {e["gate_status"] for e in state["audit"]}
        self.assertEqual({"OK", "Approval", "Hold"} & gates, {"OK", "Approval", "Hold"})
        # 住所が audit に raw で漏れていない
        dump = json.dumps(state["audit"], ensure_ascii=False)
        self.assertNotIn("霞が関", dump)
        # audit スキーマ必須フィールド
        for e in state["audit"]:
            for k in ("audit_id", "timestamp", "actor", "action", "target", "gate_status"):
                self.assertIn(k, e)

    def test_outputs_written(self):
        rows = [{"row_id": "R-001", "kind": "property", "text": "ペット可 25坪 南東向き 築10年"}]
        state = O.process(rows, self.onto)
        with tempfile.TemporaryDirectory() as d:
            out = O.write_outputs(state, d)
            for f in ("normalized_addresses.csv", "requirement_tags.csv", "condition_tags.csv",
                      "normalized_attrs.csv", "new_term_proposals.csv", "dashboard.md", "audit_log.jsonl"):
                self.assertTrue((out / f).exists(), f)
            # CSV は UTF-8 BOM
            self.assertTrue((out / "condition_tags.csv").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_unknown_kind_blocked(self):
        rows = [{"row_id": "R-001", "kind": "foobar", "text": "x"}]
        state = O.process(rows, self.onto)
        self.assertTrue(any(e["gate_status"] == "Block" for e in state["audit"]))


class TestReadRows(unittest.TestCase):
    def test_skips_guide_row(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.csv"
            p.write_text(
                "行ID,種別,入力テキスト,メモ\n"
                "例: R-001（空欄なら自動採番）,【必須】address / requirement / property / advert / term,【必須】住所…,任意メモ\n"
                "R-001,address,千代田区霞が関1丁目2番3号,\n",
                encoding="utf-8-sig")
            rows = O.read_rows(p)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["kind"], "address")

    def test_missing_header_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.csv"
            p.write_text("foo,bar\n1,2\n", encoding="utf-8")
            with self.assertRaises(O.GateError):
                O.read_rows(p)


class TestHazardVocabulary(unittest.TestCase):  # docs/RISK_BRIDGE.md の語彙橋渡しの土台
    def test_disaster_terms_present_in_ontology(self):
        # ハザード橋渡し(assess_risk)が依存する災害/ハザード語が辞書に実在することを保証
        onto = O.load_ontology()
        blob = json.dumps(onto["entries"], ensure_ascii=False)
        for kw in ("ハザードマップ", "浸水", "土砂災害警戒", "津波", "地震"):
            self.assertIn(kw, blob, f"災害/ハザード語が辞書に不在: {kw}")

    def test_chousa_domain_carries_hazard_terms(self):
        onto = O.load_ontology()
        chousa = [e for e in onto["entries"] if e.get("category") == "chousa"]
        self.assertTrue(chousa, "chousa ドメインが空")
        joined = json.dumps(chousa, ensure_ascii=False)
        self.assertTrue(any(kw in joined for kw in ("ハザード", "浸水", "土砂", "液状化")),
                        "chousa ドメインに災害/ハザード語が見当たらない")


if __name__ == "__main__":
    unittest.main()
