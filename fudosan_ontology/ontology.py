#!/usr/bin/env python3
"""fudosan-ontology — 名寄せ辞書を使った自由文→標準タグ/正規化ハーネス。

ontology.json（名寄せ辞書）を唯一の語彙源として、現場の自由文を
機械処理できる標準形に落とす。本番送信・公開・申請・決済はしない。
法令・士業・民泊可否・金銭は確定しない（不確実は要確認/null/レンジ）。統計的なスコアリング・推定はしない。

カバーする capability:
  MT-301 住所正規化           — 全角/漢数字/丁目番号のゆれを正規化
  MT-302 地番/住居表示の区別   — 正規化後の住所が地番系か住居表示系かを判別（断定不可は要確認）
  MT-006 希望条件の標準タグ化   — 顧客の希望文 → 賃料/間取り/エリア/設備/条件の標準タグ
  MT-033 ペット/楽器/民泊等の条件タグ化 — 物件/広告文 → 条件タグ（民泊可否は確定しない）
  MT-068 面積・築年・方位の表記統一 — ㎡/坪/帖・築年(和暦/西暦)・方位を統一表記へ
  MT-305 用語辞書への新語提案   — 辞書未収録の業者語候補を検出し新語提案（Hold＝人間判断）

使い方:
  python3 ontology.py sample_terms.csv --open
  python3 ontology.py --make-template
  python3 ontology.py --selftest-gate

ゲート:
  - 新語提案は必ず Hold（辞書追加は人間判断）。
  - 民泊/楽器/事務所など「可否」は広告文言の写経に留め、運用可否は確定しない（要確認）。
  - 住所は個人情報。audit_log では raw 住所を出さず target をマスクする。
  - 地番/住居表示が断定できない住所は gate=Approval（人間確認）で要確認に回す。
"""
import argparse
import csv
import io
import json
import re
import subprocess
import sys
import unicodedata
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).parent
ONTOLOGY_PATH = ROOT / "ontology.json"

# ----- 入力スキーマ -----
COLUMNS = [
    ("行ID", "row_id", "例: R-001（空欄なら自動採番）"),
    ("種別", "kind", "【必須】address / requirement / property / advert / term"),
    ("入力テキスト", "text", "【必須】住所・希望条件・物件文・広告文・用語など自由文"),
    ("メモ", "memo", "任意メモ"),
]
LABEL_TO_FIELD = {label: field for label, field, _ in COLUMNS}
KINDS = {"address", "requirement", "property", "advert", "term"}


class GateError(Exception):
    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


# ====================================================================
# 0. 辞書ロード（名寄せ index 構築）
# ====================================================================
def _alias_surface_forms(s):
    """1つの表記から、名寄せ照合に使う表層形を複数生成する。

    『三為（さんため）』のように正規形へ読み/略称を括弧併記した項目は、
    括弧前の本体（三為）と括弧内の読み（さんため）を別々のキーとして登録しないと、
    本文中の素のトークン『三為』が既知語照合に当たらず新語誤提案される（MT-305 バグ）。
    """
    s = (s or "").strip()
    forms = {s}
    # 全角/半角どちらの括弧でも本体と中身を分離。複数括弧にも対応。
    base = re.sub(r"[（(][^）)]*[）)]", "", s).strip()
    if base:
        forms.add(base)
    for inner in re.findall(r"[（(]([^）)]*)[）)]", s):
        inner = inner.strip()
        # 「俗」等の注記や空は除外。実体のある読み/略称のみ採用。
        if inner and inner not in ("俗",) and len(inner) >= 1:
            forms.add(inner)
            # 「許可の引継ぎ（俗）」のように本体側に注記を残さないため base も既に追加済み。
    return {f for f in forms if f}


def load_ontology():
    if not ONTOLOGY_PATH.exists():
        raise GateError(["ontology.json がありません。先に python3 build.py を実行してください。"])
    data = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    entries = data["entries"]
    # synonym/term → 正規形 のマップ（名寄せ）。NFKC正規化キーで引く。
    # 括弧付き読み併記は本体・読みも別キーで登録（素トークンの照合漏れ対策）。
    alias_to_term = {}
    term_to_entry = {}
    known_surfaces = set()  # 既知の表層形（部分一致判定用に保持）
    for e in entries:
        term = e["term"]
        term_to_entry[term] = e
        for surf in _alias_surface_forms(term):
            alias_to_term.setdefault(norm_key(surf), term)
            known_surfaces.add(surf)
        for s in e.get("synonyms", []):
            for surf in _alias_surface_forms(s):
                alias_to_term.setdefault(norm_key(surf), term)
                known_surfaces.add(surf)
    return {"entries": entries, "alias_to_term": alias_to_term,
            "term_to_entry": term_to_entry, "known_surfaces": known_surfaces}


def norm_key(s):
    """名寄せ照合用キー: NFKC + 小文字 + 空白/中黒/括弧除去。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower()
    s = re.sub(r"[\s・･（）()【】\[\]「」、,，。．]", "", s)
    return s


# ====================================================================
# MT-301 住所正規化 + MT-302 地番/住居表示の区別
# ====================================================================
KANJI_DIGIT = {"〇": "0", "零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
               "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
KANJI_UNIT = {"十": 10, "百": 100, "千": 1000}


def kanji_seq_to_int(seq):
    """位取りのある漢数字（例: 二十三, 千五百）を int に。失敗時 None。"""
    if not seq:
        return None
    total = 0
    current = 0
    has_unit = False
    for ch in seq:
        if ch in KANJI_DIGIT:
            current = current * 10 + int(KANJI_DIGIT[ch]) if current and ch not in ("〇", "零") else int(KANJI_DIGIT[ch])
        elif ch in KANJI_UNIT:
            has_unit = True
            unit = KANJI_UNIT[ch]
            total += (current if current else 1) * unit
            current = 0
        else:
            return None
    total += current
    if total == 0 and not has_unit and seq not in ("〇", "零"):
        return None
    return total


def _kanji_block_repl(m):
    val = kanji_seq_to_int(m.group(0))
    return str(val) if val is not None else m.group(0)


def normalize_address(raw):
    """住所文字列を正規化。丁目/番/号/番地をハイフン化し、全角/漢数字を半角数字に。

    返り値: (normalized, notes[list])
    """
    notes = []
    s = unicodedata.normalize("NFKC", raw or "").strip()
    # NFKC で全角英数→半角・全角空白→半角空白済み。連続空白を1つに。
    s = re.sub(r"[ \t]+", "", s)
    # 漢数字（位取り含む）を算用数字へ。丁目/番/号/番地/-/の の直前にある漢数字塊を対象。
    s = re.sub(r"[〇零一二三四五六七八九十百千]+(?=丁目|丁|番地|番|号|の|-|−|ー|―)", _kanji_block_repl, s)
    # 行末や区切り後の単独漢数字塊も（例: 大字○○ 二三）
    s = re.sub(r"(?<=[町村大字])[〇零一二三四五六七八九十百千]+", _kanji_block_repl, s)
    # 「丁目」「番地」「番」「号」「の」をハイフンに統一（数字に挟まれる/末尾）
    # 1丁目2番3号 → 1-2-3
    s = re.sub(r"(\d+)丁目", r"\1-", s)
    s = re.sub(r"(\d+)番地の?(\d+)", r"\1-\2", s)
    s = re.sub(r"(\d+)番地", r"\1-", s)
    s = re.sub(r"(\d+)番(\d+)号", r"\1-\2", s)
    s = re.sub(r"(\d+)番(?!地)", r"\1-", s)
    s = re.sub(r"(\d+)号(?!室|棟|館)", r"\1", s)
    s = re.sub(r"(\d+)の(\d+)", r"\1-\2", s)
    # 各種ダッシュをハイフンに統一
    s = re.sub(r"[−ー―‐－]", "-", s)
    # 連続/末尾ハイフン整理
    s = re.sub(r"-{2,}", "-", s)
    s = re.sub(r"-+$", "", s)
    s = s.strip("-") if s.endswith("-") else s
    if s != unicodedata.normalize("NFKC", raw or "").strip():
        notes.append("丁目番号/全角/漢数字を正規化")
    return s, notes


def classify_address_type(raw_normalized, raw_original):
    """住所が「住居表示」系か「地番」系かを判別。

    住居表示: 〇丁目〇番〇号（街区符号-住居番号）。実施区域で用いる公的表示。
    地番:     大字・字・〇番地〇（土地登記の番号）。建物所在地としては地番のことも。
    判定優先度:
      1) 大字/字 を含む → 地番（high）。市街地より字が強い地番シグナル。
      2) 丁目 を含む → 住居表示。号も伴えば high、なければ medium。
         （丁目は街区方式の住居表示で用いる。丁目+番地は都市部の住居表示系とみなす）
      3) 丁目なしで「号」 → 住居表示 medium。
      4) 丁目なしで「番地」（字なし）→ 地番 medium。
      5) 手掛かりなし（n-n のみ等）→ 不明・Approval（人間確認。誤判別は登記事故）。
    返り値: (type, confidence, gate, reason)
    """
    orig = unicodedata.normalize("NFKC", raw_original or "")
    s = raw_normalized
    has_chome = "丁目" in orig
    has_go = bool(re.search(r"\d+号(?!室|棟|館)", orig))
    has_banchi = "番地" in orig
    has_aza = ("大字" in orig) or bool(re.search(r"字[^\d]", orig))

    if has_aza:
        return ("地番", "high", "OK", "「大字」「字」を含む＝地番系")
    if has_chome:
        if has_go:
            return ("住居表示", "high", "OK", "丁目+番+号の3階層＝住居表示の典型")
        return ("住居表示", "medium", "OK", "「丁目」を含む（市街地の住居表示系・号は未確認）")
    if has_go:
        return ("住居表示", "medium", "OK", "「号」を含む＝住居表示の可能性が高い")
    if has_banchi:
        return ("地番", "medium", "OK", "「番地」を含み丁目/号が無い＝地番系の可能性")
    if re.search(r"\d+-\d+", s):
        return ("不明", "low", "Approval", "丁目/番地/号の語が無く地番か住居表示か断定不可（要確認）")
    return ("不明", "low", "Approval", "住所の番号体系を特定できず断定不可（要確認）")


# ====================================================================
# MT-006 希望条件の標準タグ化（顧客の希望文 → 構造化タグ）
# ====================================================================
# 末尾の \b は不可（自然文「2LDKを探す」だと を が unicode 語中文字で境界が立たず空振り）。
# 前後を「英数字でない」で挟み、地番等の誤検出を避けつつ自然文に対応する。
LAYOUT_RE = re.compile(r"(?<![0-9A-Za-z])(\d)\s*([SLDK]{1,4})(?![A-Za-z])", re.I)
RENT_RE = re.compile(r"(?:家賃|賃料|予算)?\s*([0-9]+(?:\.[0-9]+)?)\s*(万|万円)")
WALK_RE = re.compile(r"(?:駅\s*)?(?:徒歩)?\s*([0-9]+)\s*分(?:以内|まで)?")
AREA_REQ_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(㎡|平米|m2|平方メートル|帖|畳|坪)(?:以上)?")

REQ_FACILITY_TAGS = {
    "バス・トイレ別": ["バストイレ別", "ばすといれべつ", "BT別", "風呂トイレ別", "セパレート"],
    "独立洗面台": ["独立洗面", "洗面台", "洗面所独立"],
    "オートロック": ["オートロック", "autolock"],
    "宅配ボックス": ["宅配ボックス", "宅配box", "宅配ロッカー"],
    "駐車場": ["駐車場", "車庫", "ガレージ", "parking", "駐車スペース"],
    "ペット可": ["ペット可", "ペット相談", "ペットOK", "犬", "猫"],
    "2階以上": ["2階以上", "2階以上希望", "上層階", "高層階", "1階以外"],
    "エレベーター": ["エレベーター", "EV", "エレベータ"],
    "室内洗濯機置場": ["室内洗濯機", "洗濯機置場", "室内洗濯機置場"],
    "南向き": ["南向き", "南向", "日当たり", "陽当たり"],
    "都市ガス": ["都市ガス"],
    "楽器可": ["楽器可", "楽器相談", "防音", "ピアノ"],
}


def tag_requirements(text):
    """顧客の希望自由文 → 標準タグ集合 + 数値条件。"""
    nk = norm_key(text)
    tags = []
    structured = OrderedDict()
    # 間取り
    m = LAYOUT_RE.search(text.replace("ＬＤＫ", "LDK"))
    if m:
        structured["layout"] = f"{m.group(1)}{m.group(2).upper()}"
        tags.append(f"間取り:{structured['layout']}")
    # 賃料（上限とみなす）
    m = RENT_RE.search(text)
    if m:
        man = float(m.group(1))
        structured["rent_max_yen"] = int(round(man * 10000))
        tags.append(f"賃料上限:{man}万円")
    # 駅徒歩
    m = WALK_RE.search(text)
    if m:
        structured["walk_max_min"] = int(m.group(1))
        tags.append(f"駅徒歩以内:{m.group(1)}分")
    # 面積
    m = AREA_REQ_RE.search(text)
    if m:
        structured["area_min_raw"] = f"{m.group(1)}{m.group(2)}"
        tags.append(f"面積以上:{m.group(1)}{m.group(2)}")
    # 設備タグ（語彙照合）
    for tag, aliases in REQ_FACILITY_TAGS.items():
        if any(norm_key(a) in nk for a in aliases):
            tags.append(tag)
    # エリア（「○○駅」「○○区」「○○線」を抽出）。連結助詞(か/と/や/・)で区切ってから照合し、
    # 「新宿区か中野区」が1語に化けるのを防ぐ。地名本体は漢字/カタカナのみ許可。
    for seg in re.split(r"[、，,・/\sかとやのまたは及び又は]+", text):
        for a in re.findall(r"([一-龥ァ-ヶー]{1,8}(?:区|市|町|村|駅))", seg):
            tags.append(f"エリア:{a}")
            structured.setdefault("areas", []).append(a)
        for ln in re.findall(r"([一-龥ァ-ヶー]{1,8}線)", seg):
            tags.append(f"エリア:{ln}")
            structured.setdefault("areas", []).append(ln)
    return {"tags": sorted(set(tags)), "structured": structured}


# ====================================================================
# MT-033 物件/広告の条件タグ化（ペット/楽器/民泊/事務所…）
# ====================================================================
# 各条件は (可タグ, 不可タグ, 可語彙, 不可語彙, 可否確定しない=要確認)
CONDITION_RULES = [
    ("ペット", "ペット可", "ペット不可", ["ペット可", "ペット相談", "ペットOK", "犬可", "猫可", "ペット飼育可"], ["ペット不可", "ペット禁止", "ペットNG"], False),
    ("楽器", "楽器可", "楽器不可", ["楽器可", "楽器相談", "演奏可", "ピアノ可", "防音室"], ["楽器不可", "楽器禁止", "演奏不可"], False),
    ("民泊", "民泊可（要確認）", "民泊不可", ["民泊可", "民泊相談", "住宅宿泊事業可", "Airbnb可", "民泊運用可"], ["民泊不可", "民泊禁止", "住宅宿泊事業不可", "AirbnbNG"], True),
    ("事務所利用", "事務所利用可", "事務所利用不可", ["事務所可", "事務所利用可", "SOHO可", "SOHO相談", "店舗事務所可", "事業利用可"], ["事務所不可", "住居専用", "事業利用不可"], False),
    ("法人契約", "法人契約可", "法人契約不可", ["法人契約可", "法人可"], ["法人契約不可", "法人不可"], False),
]


def tag_conditions(text):
    """物件/広告自由文 → 条件タグ。可否が確定できない条件は要確認に回す。"""
    nk = norm_key(text)
    tags = []
    needs_confirm = []
    for label, ok_tag, ng_tag, ok_aliases, ng_aliases, confirm in CONDITION_RULES:
        ng_hit = any(norm_key(a) in nk for a in ng_aliases)
        ok_hit = any(norm_key(a) in nk for a in ok_aliases)
        if ng_hit:
            tags.append(ng_tag)
        elif ok_hit:
            tags.append(ok_tag)
            if confirm:
                # 民泊「可」は法令/規約/条例で運用可否が変わるため確定しない
                needs_confirm.append(f"{label}: 広告は可だが運用可否は法令/管理規約/条例で要確認（180日上限等）")
    return {"tags": sorted(set(tags)), "needs_confirm": needs_confirm}


# ====================================================================
# MT-068 面積・築年・方位の表記統一
# ====================================================================
TSUBO_TO_SQM = 3.305785
JO_SQM = 1.62  # 公正競争規約 広告上の1畳下限

# 8方位の正規化マップ（漢字2字並びの全パターン → 正規形）。
# 複合方位は「南東/東南」の双方向表記を吸収する。単方位は1字。
DIRECTION_KANJI_NORM = {
    "南東": "南東", "東南": "南東",
    "南西": "南西", "西南": "南西",
    "北東": "北東", "東北": "北東",
    "北西": "北西", "西北": "北西",
    "南": "南", "北": "北", "東": "東", "西": "西",
}
# 英字方位（NE/SW 等）。複合を単字より先に照合する。
DIRECTION_LATIN = [
    ("南東", "se"), ("南西", "sw"), ("北東", "ne"), ("北西", "nw"),
    ("南", "s"), ("北", "n"), ("東", "e"), ("西", "w"),
]
# 方位を確定してよい文脈語。これらの直前にある方位語だけを採用し、
# 地名（東口/西新宿/北区/南阿佐ヶ谷/東京都 等）の方位字を誤検出しない。
DIRECTION_CTX_RE = re.compile(
    r"([南北東西]{1,2})\s*(?:向き|向|面し?た?|採光|方角|バルコニー|ベランダ|開口)"
)
# 「採光：南東」「方角=南」のようにラベル＋区切り＋方位の形も採用する。
# また「バルコニーは南東」「主開口部が南」のように採光面を表す名詞＋助詞/区切り＋方位も採る
# （方位語が文脈名詞の後ろに来るケース。地名の方位字とは語順で区別される）。
DIRECTION_LABEL_RE = re.compile(
    r"(?:向き|方位|方角|採光|開口部?|バルコニー|ベランダ|主?居室|主?寝室|リビング|窓)"
    r"\s*(?:は|が|の)?\s*[:：=＝]?\s*([南北東西]{1,2})(?![京阪神駅口区市町村])"
)
# 英字方位は単独トークンとして（前後が英字でない）出現したときのみ採用する。
DIRECTION_LATIN_RE = re.compile(r"(?<![a-z])(se|sw|ne|nw|[nsew])(?![a-z])")
ERA_BASE = {"令和": 2018, "平成": 1988, "昭和": 1925}  # 元年=base+1
ERA_RE = re.compile(r"(令和|平成|昭和)\s*(\d+|元)\s*年")
AREA_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(㎡|平米|m2|平方メートル|坪|帖|畳)")
CHIKU_YEAR_RE = re.compile(r"築\s*([0-9]+)\s*年")
SEIREKI_RE = re.compile(r"(?:19|20)([0-9]{2})\s*年(?:築|竣工|新築)?")


def normalize_attrs(text, this_year=2026):
    """面積→㎡（坪/帖併記）・築年→西暦+築年数・方位→8方位正規形 に統一。"""
    out = OrderedDict()
    notes = []
    # 面積
    m = AREA_RE.search(text)
    if m:
        val = float(m.group(1))
        unit = unicodedata.normalize("NFKC", m.group(2))
        if unit in ("㎡", "平米", "m2", "平方メートル"):
            sqm = val
            src = f"{val}㎡"
        elif unit == "坪":
            sqm = round(val * TSUBO_TO_SQM, 2)
            src = f"{val}坪"
        else:  # 帖/畳
            sqm = round(val * JO_SQM, 2)
            src = f"{val}帖"
        out["area_sqm"] = sqm
        out["area_tsubo"] = round(sqm / TSUBO_TO_SQM, 2)
        out["area_source"] = src
        notes.append(f"面積統一: {src}→{sqm}㎡")
    # 築年
    seireki = None
    m = ERA_RE.search(unicodedata.normalize("NFKC", text))
    if m:
        era, num = m.group(1), m.group(2)
        n = 1 if num == "元" else int(num)
        seireki = ERA_BASE[era] + n
        notes.append(f"和暦→西暦: {era}{num}年→{seireki}年")
    if seireki is None:
        m = SEIREKI_RE.search(text)
        if m:
            seireki = int(m.group(0)[:4])
    chiku = CHIKU_YEAR_RE.search(text)
    if seireki is not None:
        out["built_year"] = seireki
        out["building_age"] = max(0, this_year - seireki)
        notes.append(f"築年: {seireki}年築(築{out['building_age']}年/基準{this_year})")
    elif chiku:
        age = int(chiku.group(1))
        out["building_age"] = age
        out["built_year"] = this_year - age
        notes.append(f"築年: 築{age}年→推定{out['built_year']}年(基準{this_year})")
    # 方位（向き/面/採光 等の文脈に限定。地名の「東口」「西新宿」「北区」「南阿佐ヶ谷」
    # 「東京都」を方位と誤検出しない＝全文 fallback は廃止し、文脈語直前の方位語だけ採用）。
    nfkc = unicodedata.normalize("NFKC", text)
    raw_dir = None  # 日本語方位語（1〜2字）
    m_ctx = DIRECTION_CTX_RE.search(nfkc) or DIRECTION_LABEL_RE.search(nfkc)
    if m_ctx:
        raw_dir = m_ctx.group(1)
    if raw_dir:
        # 2字なら複合方位として正規化を試み、ダメなら末尾1字で単方位へ。
        normed = DIRECTION_KANJI_NORM.get(raw_dir) or DIRECTION_KANJI_NORM.get(raw_dir[-1])
        if normed:
            out["direction"] = normed
            notes.append(f"方位統一: {normed}向き")
    else:
        # 日本語文脈が無い場合のみ、英字方位の単独トークンを採用（SE/南S等）。
        m_lat = DIRECTION_LATIN_RE.search(nfkc.lower())
        if m_lat:
            tok = m_lat.group(1)
            for normed, alias in DIRECTION_LATIN:
                if tok == alias:
                    out["direction"] = normed
                    notes.append(f"方位統一: {normed}向き（英字{tok.upper()}）")
                    break
    return {"attrs": out, "notes": notes}


# ====================================================================
# MT-305 用語辞書への新語提案（未知語検出 → Hold）
# ====================================================================
# 文法語・常用語のストップワード。業界語でない常用語が大量に新語誤提案されるのを抑える
# （MT-305: 特約/段取/業者/契約/取得/連絡 等が誤提案されていた）。固有の業界語は ontology.json
# 側で照合するため、ここは「辞書に載せる価値のない一般語」だけを並べる。
STOPWORDS = set([
    # 形式名詞・接続・助動詞由来
    "こと", "もの", "ため", "など", "それ", "これ", "あれ", "どれ", "場合", "とき", "ところ",
    "ください", "します", "しました", "ました", "して", "され", "される", "できる", "できます",
    "です", "ます", "ある", "あり", "なる", "なり", "そして", "また", "ただし", "なお", "および",
    # 不動産・取引の常用一般語（業界専門語ではなく日常語。辞書化対象外）
    "確認", "連絡", "対応", "案内", "相談", "希望", "検討", "予定", "可能", "不可", "本日", "本件",
    "本物件", "当該", "当社", "弊社", "御社", "貴社", "業者", "担当", "顧客", "先方", "今回", "今後",
    "段取", "段取り", "手配", "準備", "実施", "完了", "開始", "終了", "以上", "以下", "未満", "程度",
    "取得", "取引", "売買", "賃貸", "物件", "情報", "内容", "書類", "資料", "金額", "費用", "価格",
    "契約", "締結", "解除", "説明", "報告", "提出", "送付", "返送", "記載", "確定", "変更", "修正",
])
# 抽出: 漢字2+ / カタカナ3+ / 英字大文字3+ の塊を候補語とする
TOKEN_RE = re.compile(r"[一-龥々]{2,}|[ァ-ヶー]{3,}|[A-Za-z]{3,}")


def _is_known_fragment(tok, known_surfaces):
    """tok が既知語の表層形の一部（部分文字列）かを判定。

    例: 『特約』はそれ単体では辞書項目でないが『ローン特約/買戻特約』の構成要素であり、
    『業者』は『住宅宿泊管理業者』の一部。これらを新語提案すると精度が落ちるので除外する。
    既知語が tok を含む、または tok が既知語を含む（複合語の素片）の双方を見る。
    """
    nk = norm_key(tok)
    if len(nk) < 2:
        return False
    for surf in known_surfaces:
        ns = norm_key(surf)
        if len(ns) < 2:
            continue
        if nk in ns or ns in nk:
            return True
    return False


def propose_new_terms(text, alias_to_term, known_surfaces=None):
    """辞書未収録の業者語候補を抽出。可否は確定せず Hold（人間が辞書に追加判断）。

    過剰提案対策: (1) 文法語/常用語の STOPWORDS を除外、
    (2) 既知語の部分文字列（複合語の素片）を除外、
    (3) 括弧付き読み併記の本体・読みは load_ontology 側で別キー登録済みのため照合に当たる。
    """
    known_surfaces = known_surfaces or set()
    proposals = []
    seen = set()
    for tok in TOKEN_RE.findall(text):
        if tok in STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        if norm_key(tok) in alias_to_term:
            continue  # 既知語（正規形 or synonym or 括弧本体/読み）
        if _is_known_fragment(tok, known_surfaces):
            continue  # 既知複合語の素片（特約/業者 等）は新語にしない
        proposals.append({
            "candidate": tok,
            "kind": "kanji" if re.match(r"[一-龥々]", tok) else ("katakana" if re.match(r"[ァ-ヶー]", tok) else "latin"),
            "gate": "Hold",
            "reason": "辞書未収録。新語として追加するか人間が判断（同義語化/別概念/誤抽出）",
        })
    return proposals


# ====================================================================
# 入力読み込み
# ====================================================================
def make_template():
    path = ROOT / "input_template.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([label for label, _, _ in COLUMNS])
        writer.writerow([guide for _, _, guide in COLUMNS])
    print(f"記入用テンプレートを生成: {path}")


def decode_csv_bytes(raw):
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise GateError(["文字コードを判定できません。UTF-8(BOM)またはShift_JIS(cp932)で保存してください。"])


def read_rows(path):
    raw = Path(path).read_bytes()
    text = decode_csv_bytes(raw)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise GateError(["入力CSVが空です。"])
    header = [h.strip() for h in rows[0]]
    field_idx = {}
    for i, h in enumerate(header):
        if h in LABEL_TO_FIELD:
            field_idx[LABEL_TO_FIELD[h]] = i
    if "kind" not in field_idx or "text" not in field_idx:
        raise GateError(["ヘッダに『種別』と『入力テキスト』が必要です。--make-template を参照。"])
    out = []
    for r_i, row in enumerate(rows[1:], start=1):
        get = lambda fld: (row[field_idx[fld]].strip() if fld in field_idx and field_idx[fld] < len(row) else "")
        kind = get("kind")
        text = get("text")
        if not kind and not text:
            continue
        # 2行目がガイド行（種別が KINDS でない説明文）ならスキップ
        if kind not in KINDS and ("/" in kind or "必須" in kind or kind == ""):
            continue
        out.append({
            "row_id": get("row_id") or f"R-{r_i:03d}",
            "kind": kind,
            "text": text,
            "memo": get("memo"),
        })
    if not out:
        raise GateError(["処理対象の行がありません。種別/入力テキストを記入してください。"])
    return out


# ====================================================================
# 処理本体
# ====================================================================
def process(rows, onto, this_year=2026):
    addresses, requirements, conditions, attrs, proposals, audit = [], [], [], [], [], []
    holds = []
    seq = 0

    def add_audit(action, target, gate_status, **detail):
        nonlocal seq
        seq += 1
        e = {
            "audit_id": f"ONT-AUD-{seq:04d}",
            "timestamp": f"seq:{seq:04d}",  # 外部時刻を読まない（決定的・no-network）
            "actor": "fudosan-ontology",
            "action": action,
            "target": target,
            "gate_status": gate_status,
        }
        e.update(detail)
        audit.append(e)

    for row in rows:
        rid, kind, text = row["row_id"], row["kind"], row["text"]
        if kind not in KINDS:
            add_audit("skip_unknown_kind", rid, "Block", note=f"未知の種別: {kind}")
            continue

        if kind == "address":
            normalized, n_notes = normalize_address(text)
            atype, conf, gate, reason = classify_address_type(normalized, text)
            addresses.append({
                "row_id": rid, "normalized": normalized, "address_type": atype,
                "confidence": conf, "gate": gate, "reason": reason,
                "notes": "; ".join(n_notes),
            })
            # 住所は個人情報 → audit には raw を出さずマスク
            add_audit("address_normalize_classify", f"{rid}/<addr:masked>", gate,
                      address_type=atype, confidence=conf)
            if gate == "Approval":
                holds.append(f"[{rid}] 住所の地番/住居表示が断定不可（要確認）: {normalized}")

        elif kind == "requirement":
            res = tag_requirements(text)
            requirements.append({"row_id": rid, "tags": " / ".join(res["tags"]),
                                 "structured": json.dumps(res["structured"], ensure_ascii=False)})
            add_audit("requirement_tagging", rid, "OK", tag_count=len(res["tags"]))

        elif kind in ("property", "advert"):
            cres = tag_conditions(text)
            ares = normalize_attrs(text, this_year=this_year)
            conditions.append({"row_id": rid, "kind": kind,
                               "condition_tags": " / ".join(cres["tags"]),
                               "needs_confirm": " | ".join(cres["needs_confirm"])})
            attrs.append({"row_id": rid, "kind": kind,
                          "attrs": json.dumps(ares["attrs"], ensure_ascii=False),
                          "notes": "; ".join(ares["notes"])})
            gate = "Approval" if cres["needs_confirm"] else "OK"
            add_audit("condition_attr_tagging", rid, gate,
                      condition_count=len(cres["tags"]))
            for c in cres["needs_confirm"]:
                holds.append(f"[{rid}] {c}")

        elif kind == "term":
            props = propose_new_terms(text, onto["alias_to_term"], onto.get("known_surfaces"))
            for p in props:
                p2 = dict(p, row_id=rid)
                proposals.append(p2)
                add_audit("new_term_proposal", f"{rid}/{p['candidate']}", "Hold",
                          candidate=p["candidate"])
                holds.append(f"[{rid}] 新語提案『{p['candidate']}』→ 辞書追加可否を人間判断(Hold)")
            if not props:
                add_audit("new_term_proposal", rid, "OK", note="未知語なし")

    return {
        "addresses": addresses, "requirements": requirements, "conditions": conditions,
        "attrs": attrs, "proposals": proposals, "holds": holds, "audit": audit,
    }


# ====================================================================
# 出力
# ====================================================================
def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[key for _, key in columns])
        writer.writerow({key: label for label, key in columns})
        for row in rows:
            writer.writerow({key: row.get(key, "") for _, key in columns})


def write_outputs(state, out_dir=None):
    out = Path(out_dir) if out_dir else Path.cwd() / "out"
    out.mkdir(exist_ok=True)
    write_csv(out / "normalized_addresses.csv", state["addresses"], [
        ("行ID", "row_id"), ("正規化住所", "normalized"), ("住所種別", "address_type"),
        ("確度", "confidence"), ("ゲート", "gate"), ("判定根拠", "reason"), ("正規化メモ", "notes")])
    write_csv(out / "requirement_tags.csv", state["requirements"], [
        ("行ID", "row_id"), ("標準タグ", "tags"), ("構造化条件", "structured")])
    write_csv(out / "condition_tags.csv", state["conditions"], [
        ("行ID", "row_id"), ("種別", "kind"), ("条件タグ", "condition_tags"), ("要確認", "needs_confirm")])
    write_csv(out / "normalized_attrs.csv", state["attrs"], [
        ("行ID", "row_id"), ("種別", "kind"), ("統一属性", "attrs"), ("統一メモ", "notes")])
    write_csv(out / "new_term_proposals.csv", state["proposals"], [
        ("行ID", "row_id"), ("候補語", "candidate"), ("種類", "kind"), ("ゲート", "gate"), ("理由", "reason")])
    with (out / "audit_log.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for e in state["audit"]:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    (out / "dashboard.md").write_text(render_dashboard(state), encoding="utf-8")
    return out


def render_dashboard(state):
    gate_counts = Counter(e["gate_status"] for e in state["audit"])
    lines = [
        "# fudosan-ontology Dashboard",
        "",
        "名寄せ辞書（ontology.json）による自由文→標準タグ/正規化の処理結果。",
        "本ハーネスは送信・公開・申請・決済をしない。民泊可否・士業・法令は確定しない（要確認）。",
        "",
        "## Summary",
        "",
        "| 指標 | 件数 |",
        "|---|---:|",
        f"| 住所正規化 | {len(state['addresses'])} |",
        f"| 希望条件タグ化 | {len(state['requirements'])} |",
        f"| 物件/広告 条件タグ化 | {len(state['conditions'])} |",
        f"| 面積/築年/方位 統一 | {len(state['attrs'])} |",
        f"| 新語提案(Hold) | {len(state['proposals'])} |",
        f"| Hold/要確認 | {len(state['holds'])} |",
        "",
        "## ゲート状況",
        "",
        "| gate_status | 件数 |",
        "|---|---:|",
    ]
    for g, c in sorted(gate_counts.items()):
        lines.append(f"| {g} | {c} |")
    lines += ["", "## Hold / 要確認（人間判断が必要）", ""]
    if state["holds"]:
        for h in state["holds"]:
            lines.append(f"- {h}")
    else:
        lines.append("- なし")
    lines += ["", "## 成果物", "",
              "- `normalized_addresses.csv` — 正規化住所＋地番/住居表示判定",
              "- `requirement_tags.csv` — 希望条件の標準タグ",
              "- `condition_tags.csv` — ペット/楽器/民泊/事務所等の条件タグ",
              "- `normalized_attrs.csv` — 面積(㎡/坪)・築年(西暦/築年数)・方位の統一",
              "- `new_term_proposals.csv` — 辞書未収録の新語候補（Hold＝追加は人間判断）",
              "- `audit_log.jsonl` — 監査証跡（住所はマスク）"]
    return "\n".join(lines) + "\n"


# ====================================================================
# selftest（自明でない実テスト）
# ====================================================================
def selftest():
    onto = load_ontology()
    # MT-301: 住所正規化
    n, _ = normalize_address("東京都千代田区霞が関一丁目２番３号")
    assert n.endswith("霞が関1-2-3"), n
    n2, _ = normalize_address("大阪府大阪市北区梅田３丁目１番地の２")
    assert n2.endswith("梅田3-1-2"), n2
    # MT-302: 地番/住居表示の区別
    t, c, g, _ = classify_address_type("a", "千代田区霞が関1丁目2番3号")
    assert t == "住居表示" and c == "high" and g == "OK", (t, c, g)
    # 丁目+番地（都市部）は住居表示系へ（大字字より丁目を優先しない＝地番誤判別を回避）
    t_u, c_u, g_u, _ = classify_address_type("梅田3-1-2", "梅田3丁目1番地の2")
    assert t_u == "住居表示", (t_u, c_u)
    t2, c2, g2, _ = classify_address_type("x", "○○市大字田中字山1234番地2")
    assert t2 == "地番" and c2 == "high", (t2, c2)
    # 字なしの番地のみ → 地番系
    t2b, c2b, _, _ = classify_address_type("田中1234-2", "田中1234番地2")
    assert t2b == "地番", t2b
    t3, c3, g3, _ = classify_address_type("町名1-2", "町名1-2")
    assert t3 == "不明" and g3 == "Approval", (t3, g3)
    # MT-006: 希望条件タグ化
    req = tag_requirements("家賃8万以内、2LDK、駅徒歩10分以内、バス・トイレ別、ペット相談、新宿区希望")
    assert req["structured"]["rent_max_yen"] == 80000, req["structured"]
    assert req["structured"]["layout"] == "2LDK"
    assert req["structured"]["walk_max_min"] == 10
    assert "バス・トイレ別" in req["tags"]
    assert "ペット可" in req["tags"]
    assert any(t.startswith("エリア:新宿区") for t in req["tags"]), req["tags"]
    # MT-033: 条件タグ化（民泊可は要確認になる）
    cond = tag_conditions("ペット相談可、楽器不可、民泊相談可、SOHO可")
    assert "ペット可" in cond["tags"]
    assert "楽器不可" in cond["tags"]
    assert "民泊可（要確認）" in cond["tags"]
    assert "事務所利用可" in cond["tags"]
    assert cond["needs_confirm"], "民泊可は運用可否を確定せず要確認に回すべき"
    # MT-068: 面積/築年/方位統一
    a = normalize_attrs("専有面積25坪、平成2年築、南東向き")
    assert abs(a["attrs"]["area_sqm"] - round(25 * TSUBO_TO_SQM, 2)) < 0.01
    assert a["attrs"]["built_year"] == 1990, a["attrs"]
    assert a["attrs"]["building_age"] == 2026 - 1990
    assert a["attrs"]["direction"] == "南東"
    a2 = normalize_attrs("約12帖、築15年、東南向きバルコニー")
    assert abs(a2["attrs"]["area_sqm"] - round(12 * JO_SQM, 2)) < 0.01
    assert a2["attrs"]["built_year"] == 2011
    assert a2["attrs"]["direction"] == "南東"
    # MT-068 バグ修正: 文脈語が無い地名の方位字は方位として採用しない（誤検出抑制）
    assert normalize_attrs("東口徒歩5分、西新宿、北区").get("attrs").get("direction") is None
    assert normalize_attrs("バルコニーは南東").get("attrs").get("direction") == "南東"
    # MT-305: 新語提案（既知語は除外、未知語のみ Hold）
    ks = onto.get("known_surfaces")
    props = propose_new_terms("マイソクを送って。フガフガとゲンナマ決済について。", onto["alias_to_term"], ks)
    cands = [p["candidate"] for p in props]
    assert "マイソク" not in cands, "既知語が提案に混入"
    assert all(p["gate"] == "Hold" for p in props)
    assert any(c in cands for c in ("フガフガ", "ゲンナマ")), cands
    # MT-305 バグ修正: 括弧付き読み併記の既知語（三為（さんため））と常用語の誤提案を防ぐ
    props2 = propose_new_terms("本物件は三為（さんため）契約です。特約を確認し業者に連絡。",
                               onto["alias_to_term"], ks)
    c2 = [p["candidate"] for p in props2]
    assert "三為" not in c2, f"括弧付き読み併記の既知語が誤提案: {c2}"
    assert "特約" not in c2, f"既知複合語の素片が誤提案: {c2}"
    assert "業者" not in c2 and "契約" not in c2 and "本物件" not in c2, f"常用語が誤提案: {c2}"
    # ゲート発火を含む統合テスト
    rows = [
        {"row_id": "R-001", "kind": "address", "text": "千代田区霞が関一丁目2番3号"},
        {"row_id": "R-002", "kind": "address", "text": "町名2-3"},
        {"row_id": "R-003", "kind": "requirement", "text": "1LDK 家賃10万 ペット可"},
        {"row_id": "R-004", "kind": "property", "text": "民泊相談可、南向き、築20年"},
        {"row_id": "R-005", "kind": "term", "text": "ナゾノゴ という用語"},
    ]
    state = process(rows, onto)
    gates = {e["gate_status"] for e in state["audit"]}
    assert "Hold" in gates and "Approval" in gates and "OK" in gates, gates
    # 住所マスク確認
    assert all("霞が関" not in json.dumps(e, ensure_ascii=False) for e in state["audit"]), "raw住所がauditに漏洩"
    out = write_outputs(state)
    assert (out / "dashboard.md").exists()
    assert (out / "audit_log.jsonl").exists()
    assert (out / "normalized_addresses.csv").exists()
    print("✓ selftest pass (MT-006/033/068/301/302/305 gates fired)")


def main(argv=None):
    parser = argparse.ArgumentParser(description="fudosan-ontology 名寄せ辞書ハーネス")
    parser.add_argument("input", nargs="?", help="入力CSV（種別/入力テキスト）")
    parser.add_argument("--out", default=None)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--make-template", action="store_true")
    parser.add_argument("--selftest-gate", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.make_template:
            make_template()
            return 0
        if args.selftest_gate:
            selftest()
            return 0
        if not args.input:
            raise GateError(["入力CSVを指定してください。例: python3 ontology.py sample_terms.csv --open"])
        onto = load_ontology()
        rows = read_rows(args.input)
        state = process(rows, onto)
        out = write_outputs(state, args.out)
        print(f"✓ fudosan-ontology出力: {out}")
        print(f"  住所 {len(state['addresses'])} / 希望 {len(state['requirements'])} / 条件 {len(state['conditions'])} / 属性 {len(state['attrs'])} / 新語提案 {len(state['proposals'])} / Hold {len(state['holds'])}")
        if args.open:
            subprocess.run(["open", str(out / "dashboard.md")], check=False)
        return 0
    except GateError as e:
        print("入力エラー:", file=sys.stderr)
        for err in e.errors:
            print(f"- {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
