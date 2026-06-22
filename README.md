🌐 **日本語** | [English](README.en.md)

# fudosan-ontology

> ### ▶️ **[377 語の辞書をブラウズする](ontology.md)** 👈

日本の不動産（宅建業）の**業界用語・表記ゆれ・略語**を、機械が扱える標準形に名寄せする
オープンな語彙辞書。**377 語 / 10 ドメイン / 2,400+ エイリアス**。
AI から自然言語で引ける **MCP サーバ同梱**。

**v1** ・ MIT License ・ Python 3 標準ライブラリのみ ・ **ネットワーク呼出なし（全ローカル）**

---

## なぜ fudosan-ontology？

不動産の現場では、同じ概念が会社・ポータル・担当者ごとにバラバラの言葉で書かれます
（`マイソク` / `物件概要書` / `販売図面`、`さんため` / `三為`、`築15年` / `平成23年築`）。
標準化された共通語彙が公共財として無いため、AI・OCR・データ連携のたびに各社が
名寄せ辞書を一から作り直しています。それを **1 つのオープンな辞書**にします。

| | 自前で実装 | 各社の独自辞書 | **fudosan-ontology** |
|---|:---:|:---:|:---:|
| 377 語 / 10 ドメインの網羅 | 都度 | バラバラ | **✅** |
| 表記ゆれ・略語の名寄せ | 自作 | 社内のみ | **✅ 2,400+ エイリアス** |
| AI から呼べる (MCP) | ❌ | ❌ | **✅ 同梱** |
| セルフホスト・PII 手元 | – | – | **✅ ネットワークなし** |
| 法令出典つき（参考） | 都度 | 不明 | **✅ 参考ポインタ** |
| コスト | 工数 | ライセンス費 | **0 円** |
| ソースコード | – | 非公開 | **MIT（このリポ）** |

---

## クイックスタート

### 30 秒で試す

```bash
git clone https://github.com/shoeiiwaya/fudosan-ontology.git
cd fudosan-ontology
python3 ontology.py --selftest-gate
```

期待される出力:

```
✓ selftest pass (MT-006/033/068/301/302/305 gates fired)
```

依存ゼロ（Python 3 標準ライブラリのみ）。インストール不要・ネットワーク不要。

### 用語を名寄せする（Python）

```python
import ontology as O
onto = O.load_ontology()

term = onto["alias_to_term"][O.norm_key("さんため")]
print(term)                                      # => 三為（さんため）
print(onto["term_to_entry"][term]["category"])   # => baibai
```

### 自由文を標準形に落とす（ハーネス）

```bash
python3 ontology.py --make-template     # 記入用 input_template.csv を生成
python3 ontology.py sample_terms.csv    # 入力CSVを処理 → out/ に成果物
```

---

## 主要機能

### 📖 辞書（`ontology.json`）
- **377 語 / 10 ドメイン** — 売買・賃貸・物件表記・登記・調査・契約・収益・旅館・金融・現場語
- **2,400+ エイリアス** — 漢字/カナ/英字・全角半角・送り仮名・略語の表記ゆれを正規形へ
- **バイリンガル** — 業者向け定義 `definition_pro` / 顧客向けやさしい定義 `definition_plain` / 英訳 `english`
- **法令出典つき** — 参考条文ポインタ `legal_source`（→ [法的免責](#法的免責重要)）

### 🔤 名寄せ・正規化ハーネス（`ontology.py`）
- **住所正規化** (MT-301) — 全角/漢数字/丁目・番・号 → 半角ハイフン統一
- **地番 / 住居表示の判別** (MT-302) — 断定不可は要確認ゲートへ
- **希望条件のタグ化** (MT-006) — 賃料/間取り/駅徒歩/面積/設備/エリア
- **ペット・楽器・民泊等の条件タグ化** (MT-033) — 可否は確定しない（要確認）
- **面積・築年・方位の表記統一** (MT-068) — 坪/帖→㎡、和暦/西暦/築N年、8方位
- **辞書への新語提案** (MT-305) — 追加可否は人間判断（Hold）

### 🤖 MCP サーバ（`mcp_server.py`）
- `resolve_term` — 用語 → 正規形 + 定義 + カテゴリ + 同義語 + 英訳 + 法令出典
- `normalize` — 自由文 → 標準タグ・正規化値（ハーネスと同一ロジック）
- `assess_risk` — 住所 → 災害/ハザード語彙（外部リスク評価 API 接続はスタブ）
- 改行区切り JSON-RPC・標準ライブラリのみ・ネットワーク呼出なし

### 🛡️ 設計の約束
- 法令・可否・金額を**確定しない**（不確実は要確認 / `null`）
- 住所は個人情報 → 監査ログでマスク
- 出典をでっち上げない・免責を明示（→ [法的免責](#法的免責重要)）

---

## アーキテクチャ

```
現場の自由文 ──▶ [ ontology.py ハーネス ] ──▶ 標準タグ / 正規化値 / 監査ログ
                          ▲
                  [ ontology.json 辞書 ]
                  377 語 / 2,400+ エイリアス / 10 ドメイン
                          ▲
            [ mcp_server.py ]  ⇄  Claude 等の AI / MCP クライアント
```

すべて Python 標準ライブラリのみ・全ローカル・ネットワーク呼出なし。

---

## MCP 登録（Claude Code / Claude Desktop 等）

```json
{
  "mcpServers": {
    "fudosan-ontology": { "command": "python3", "args": ["/abs/path/to/fudosan-ontology/mcp_server.py"] }
  }
}
```

```bash
python3 mcp_server.py     # stdin/stdout で MCP クライアントと接続
python3 test_mcp.py       # 実ツール呼び出しの検証
```

---

## ドキュメント

- [SPEC.md](SPEC.md) — ハーネス仕様・capability 対応表・ゲート定義
- [docs/RISK_BRIDGE.md](docs/RISK_BRIDGE.md) — 災害/ハザード語彙を外部リスク評価 API に橋渡しする接続仕様
- [docs/verification-log.md](docs/verification-log.md) — 法令出典・換算定数の確証記録
- [MANIFESTO.md](MANIFESTO.md) — なぜ無料で公開するのか

---

## 辞書を更新する（コントリビュート）

1. `domains/<key>.json` にエントリを追加・修正
2. `python3 build.py` で統合・衝突検出
3. `python3 ontology.py --selftest-gate` と `python3 test_ontology.py` が緑であることを確認
4. Pull Request

**新しい同義語・表記ゆれの追加が、辞書を最も速く育てます。** Issue / PR 歓迎。

---

## 法的免責（重要）

本辞書の定義（`definition_pro` / `definition_plain`）および法令出典（`legal_source`）は、
不動産実務の理解を助ける**参考情報**であり、**法的助言ではありません**。

- `legal_source` の条文は、辞書生成時に出典の実在を確認した**参考ポインタ**です（民法・建築基準法・
  不動産登記法・宅地建物取引業法・借地借家法・都市計画法 等、約 200 件）。**最新の条文・改正・
  解釈を保証するものではありません。**
- 重要事項説明・契約・申請・税務など、**法的効果を伴う場面で用いる前に、必ず現行法令の原文と
  専門家（弁護士・税理士・宅地建物取引士 等）に確認してください。**
- ハーネスが実行時ロジックで法令に依拠するのは 2 点のみで、これらは独立に再確認済みです
  （[docs/verification-log.md](docs/verification-log.md)）。エントリの `legal_source` はそれとは別の
  参考メタデータです。

本辞書を利用したことによる一切の結果について、作者は責任を負いません（MIT ライセンス「AS IS」）。

---

## ライセンス

[MIT License](LICENSE) — Copyright (c) 2026 株式会社理 (Kotowari Inc.)

---

> **fudosan-ontology** by [@shoeiiwaya](https://github.com/shoeiiwaya) — 不動産の共通語彙を、オープンに。
