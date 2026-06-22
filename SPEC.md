# fudosan-ontology SPEC — 名寄せ辞書ハーネス

`ontology.json`（名寄せ辞書）を唯一の語彙源として、
現場の自由文を機械処理できる標準形に落とす gated ハーネス。

## 理ツール標準（厳守）

- stdlib のみ・全ローカル・外部ネットワーク禁止（requests/urllib.request.urlopen/selenium/playwright/socket 不使用）。
- 本番送信・公開・申請・決済をしない。
- 法令・士業・金銭・個人情報・価格を確定しない（不確実は要確認 / null / レンジ）。
- 統計的なスコアリング・確率推定はしない（語彙の正規化のみ）。
- 出力は UTF-8(BOM) CSV ＋ `out/dashboard.md` ＋ `out/audit_log.jsonl`
  （`audit_id` / `timestamp` / `actor` / `action` / `target` / `gate_status`）。
- `ontology.py` に `--make-template` と `--selftest-gate` を維持。

## エントリポイント

```
python3 ontology.py --make-template       # 記入用 input_template.csv を生成
python3 ontology.py sample_terms.csv       # 入力CSVを処理し out/ に成果物
python3 ontology.py --selftest-gate        # 内蔵セルフテスト（全 capability のゲート発火を検証）
python3 build.py                           # domains/*.json → ontology.json/md 再生成
```

入力CSV列: `行ID, 種別, 入力テキスト, メモ`。
種別 = `address | requirement | property | advert | term`。

## カバーする capability（coverage_matrix.json）

| MT-id | タイトル | 種別 | 実装 |
|---|---|---|---|
| MT-301 | 住所正規化 | address | 全角/漢数字（位取り含む）→半角、丁目/番/番地/号/の →ハイフン統一、ダッシュ正規化 |
| MT-302 | 地番/住居表示の区別 | address | 大字字＝地番high・丁目＝住居表示・番地のみ＝地番medium・手掛かりなし＝不明/Approval |
| MT-006 | 希望条件の標準タグ化 | requirement | 賃料上限/間取り/駅徒歩/面積を構造化＋設備タグ（辞書照合）＋エリア抽出 |
| MT-033 | ペット/楽器/民泊等の条件タグ化 | property/advert | 可否タグ。可否は不可優先。民泊「可」は運用可否を確定せず要確認(Approval) |
| MT-068 | 面積・築年・方位の表記統一 | property/advert | 坪/帖→㎡（坪併記）、和暦/西暦/築N年→西暦+築年数、8方位正規化（複合方位優先）。方位は「向き/採光/方角/開口/バルコニー」等の文脈語に隣接した方位語のみ採用し、地名の方位字（東口/西新宿/北区/南阿佐ヶ谷/東京）は誤検出しない（全文 fallback 廃止） |
| MT-305 | 用語辞書への新語提案 | term | 辞書未収録の業者語候補を抽出し新語提案。追加可否は人間判断（Hold）。括弧付き読み併記の既知語（例『三為（さんため）』）は本体・読みを別キー登録して照合漏れを防ぎ、常用語/既知複合語の素片（特約/業者/契約 等）は提案しない |

## ゲート（Hold / Approval / Block）

- **新語提案** → 常に `Hold`（辞書追加は人間判断）。
- **民泊「可」など運用可否** → `Approval`（住宅宿泊事業法180日上限・管理規約・自治体条例・近隣同意で変わるため確定しない）。
- **地番/住居表示が断定不可な住所** → `Approval`（誤判別は登記事故）。
- **未知の種別** → `Block`。
- **住所は個人情報** → `audit_log` では raw 住所を出さず `target` をマスク（`<addr:masked>`）。

## 出力（out/）

- `normalized_addresses.csv` — 正規化住所＋地番/住居表示判定＋確度＋ゲート
- `requirement_tags.csv` — 希望条件の標準タグ＋構造化条件(JSON)
- `condition_tags.csv` — 物件/広告の条件タグ＋要確認
- `normalized_attrs.csv` — 面積(㎡/坪)・築年(西暦/築年数)・方位の統一(JSON)
- `new_term_proposals.csv` — 辞書未収録の新語候補（Hold）
- `dashboard.md` — サマリ・ゲート状況・Hold/要確認一覧
- `audit_log.jsonl` — 監査証跡（住所マスク）

## 法令出典（legal_source）の扱い

`legal_source` は**参考条文ポインタ**。出典をでっち上げず、不確実なものは `null`。
ただし参考であり最新性・正確性は保証しない＝**法的助言ではない**（→ README「法的免責」）。
法的効果を伴う場面で用いる前に現行法令の原文と専門家に確認すること。

**ハーネス（`ontology.py`）が実行時ロジックで法令に依拠するのは** `domains/conditions.json` の
次の2点のみ（これらは `docs/verification-log.md` で独立に再確認済み）:
- 住宅宿泊事業法第2条第3項（年間提供日数180日以内）→ 民泊「可」を Approval に回す根拠
- 不動産の表示に関する公正競争規約（広告上1畳=1.62㎡以上）→ 帖→㎡ 換算係数 JO_SQM=1.62 の根拠

辞書エントリ全体の `legal_source`（民法・建築基準法・不動産登記法・宅地建物取引業法・借地借家法 等、
約200件）は、上記の実行時ロジックとは別の**参考メタデータ**であり、v1 生成時に出典の実在を
確認した参考ポインタとして提供する。検証範囲の詳細は `docs/verification-log.md`。

## 決定性

`timestamp` は外部時刻を読まず入力由来の連番（`seq:NNNN`）。no-network・再現可能。
築年計算の基準年は `this_year`（既定2026）を引数で固定可能。
