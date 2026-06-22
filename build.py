#!/usr/bin/env python3
"""domains/*.json を統合して ontology.json / ontology.md を生成する。

- term 完全一致は1エントリに統合（synonyms は和集合、legal_source は非null優先）
- ある語の synonym が別エントリの term と衝突した場合は collision として報告
  （名寄せ辞書としては「どちらの正規形に寄せるか」の人間判断が必要なため）
"""
import json
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).parent
DOMAINS_DIR = ROOT / "domains"

CATEGORY_LABELS = OrderedDict([
    ("baibai", "売買仲介・取引"),
    ("chintai", "賃貸仲介・管理"),
    ("hyoki", "物件表記・広告・図面"),
    ("touki", "登記・権利関係"),
    ("chousa", "物件調査・法令制限"),
    ("keiyaku", "契約・重説・決済"),
    ("shueki", "収益物件・投資"),
    ("ryokan", "旅館・宿泊・転用"),
    ("kinyu", "金融・税務"),
    ("slang", "業界スラング・現場語"),
])


def load_entries():
    entries = []
    for path in sorted(DOMAINS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data["entries"] if isinstance(data, dict) else data
        for e in items:
            e.setdefault("synonyms", [])
            e.setdefault("related_terms", [])
            e.setdefault("legal_source", None)
            e.setdefault("caution", None)
            if e.get("category") not in CATEGORY_LABELS:
                e["category"] = "baibai"
            entries.append(e)
    return entries


def merge(entries):
    by_term = OrderedDict()
    for e in entries:
        key = e["term"].strip()
        if key not in by_term:
            e["term"] = key
            by_term[key] = e
            continue
        prev = by_term[key]
        prev["synonyms"] = sorted(set(prev["synonyms"]) | set(e["synonyms"]))
        prev["related_terms"] = sorted(set(prev["related_terms"]) | set(e["related_terms"]))
        if not prev.get("legal_source") and e.get("legal_source"):
            prev["legal_source"] = e["legal_source"]
        if not prev.get("caution") and e.get("caution"):
            prev["caution"] = e["caution"]
    return list(by_term.values())


def apply_resolutions(merged):
    """resolutions.json の merges/unlinks を適用（衝突解決の判断記録を再現可能にする）"""
    res_path = ROOT / "resolutions.json"
    if not res_path.exists():
        return merged
    res = json.loads(res_path.read_text(encoding="utf-8"))
    by_term = {e["term"]: e for e in merged}

    for m in res.get("merges", []):
        into = by_term.get(m["into"])
        if not into:
            continue
        for src_term in m["from"]:
            src = by_term.pop(src_term, None)
            if not src:
                continue
            into["synonyms"] = sorted(
                (set(into["synonyms"]) | set(src["synonyms"]) | {src_term}) - {into["term"]})
            into["related_terms"] = sorted(
                (set(into["related_terms"]) | set(src["related_terms"])) - {into["term"]})
            if not into.get("legal_source") and src.get("legal_source"):
                into["legal_source"] = src["legal_source"]
            if not into.get("caution") and src.get("caution"):
                into["caution"] = src["caution"]

    for u in res.get("unlinks", []):
        e = by_term.get(u["term"])
        if not e:
            continue
        s = u["remove_synonym"]
        if s in e["synonyms"]:
            e["synonyms"].remove(s)
            if s not in e["related_terms"]:
                e["related_terms"] = sorted(set(e["related_terms"]) | {s})

    # 自己参照と、統合で消えた語へのsynonym残骸を掃除
    for e in by_term.values():
        e["synonyms"] = sorted(set(e["synonyms"]) - {e["term"]})
    return list(by_term.values())


def find_collisions(merged):
    term_set = {e["term"] for e in merged}
    collisions = []
    for e in merged:
        for s in e["synonyms"]:
            s = s.strip()
            if s in term_set and s != e["term"]:
                collisions.append({"term": e["term"], "synonym": s,
                                   "issue": "synonym が別エントリの正規形と衝突（正規形の一本化要判断）"})
    return collisions


def write_outputs(merged, collisions):
    merged.sort(key=lambda e: (list(CATEGORY_LABELS).index(e["category"]), e.get("reading", "")))
    out = {
        "name": "不動産 業界用語・名寄せオントロジー",
        "version": "v1",
        "owner": "株式会社理 (Kotowari Inc.)",
        "license": "MIT",
        "disclaimer": (
            "定義および legal_source は参考情報であり法的助言ではありません。"
            "legal_source は生成時に出典の実在を確認した参考条文ポインタで、最新性・正確性は保証しません。"
            "法的効果を伴う利用の前に現行法令の原文と専門家に確認してください。詳細は README『法的免責』。"
        ),
        "legal_source_policy": (
            "reference-pointer; not legal advice; verify against current statutes before official use"
        ),
        "term_count": len(merged),
        "categories": dict(CATEGORY_LABELS),
        "entries": merged,
        "collisions_pending": collisions,
    }
    (ROOT / "fudosan_ontology" / "ontology.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# 不動産 業界用語・名寄せオントロジー v1", "",
             f"全 {len(merged)} 語。正本は `ontology.json`（このファイルは閲覧用インデックス）。", ""]
    for cat, label in CATEGORY_LABELS.items():
        items = [e for e in merged if e["category"] == cat]
        if not items:
            continue
        lines.append(f"## {label}（{len(items)}語）")
        lines.append("")
        lines.append("| 用語 | 読み | 同義語・表記ゆれ | 顧客向け説明 | 法的出典 |")
        lines.append("|---|---|---|---|---|")
        for e in items:
            syn = "、".join(e["synonyms"][:6]) + ("…" if len(e["synonyms"]) > 6 else "")
            src = e.get("legal_source") or "—"
            plain = e["definition_plain"].replace("|", "／").replace("\n", " ")
            lines.append(f"| **{e['term']}** | {e.get('reading','')} | {syn} | {plain} | {src} |")
        lines.append("")
    if collisions:
        lines.append("## ⚠️ 名寄せ衝突（要人間判断）")
        lines.append("")
        for c in collisions:
            lines.append(f"- 「{c['term']}」の synonym「{c['synonym']}」が独立エントリと衝突")
        lines.append("")
    (ROOT / "ontology.md").write_text("\n".join(lines), encoding="utf-8")


def sync_node_data():
    """Node パッケージ用 data/ を辞書と同期（辞書コピー + Python と同一規則の alias 索引）。"""
    import shutil
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    shutil.copy(ROOT / "fudosan_ontology" / "ontology.json", data_dir / "ontology.json")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from fudosan_ontology import ontology as O
    onto = O.load_ontology()
    (data_dir / "alias_index.json").write_text(
        json.dumps(onto["alias_to_term"], ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")


def main():
    entries = load_entries()
    merged = merge(entries)
    merged = apply_resolutions(merged)
    collisions = find_collisions(merged)
    write_outputs(merged, collisions)
    sync_node_data()
    per_cat = {}
    for e in merged:
        per_cat[e["category"]] = per_cat.get(e["category"], 0) + 1
    print(f"raw={len(entries)} merged={len(merged)} collisions={len(collisions)}")
    for cat, label in CATEGORY_LABELS.items():
        print(f"  {label}: {per_cat.get(cat, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
