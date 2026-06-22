🌐 **日本語** | [English](README.en.md)

# fudosan-ontology

> ### ▶️ **[30 秒で試す](#クイックスタート)** ・ [辞書を引く](ontology.md) 👈

不動産（宅建業）の現場テキスト — 物確メモ・反響・広告文・OCR データ — を、
AI が**業者語のまま読んで標準形に整える**オープンな**業務効率化ツール**。
表記ゆれ・略語・住所/面積/築年の不統一を機械が名寄せ。**377 語の辞書を内蔵**し、
Claude などの AI から **MCP で直接**呼べる。

**v1** ・ MIT License ・ Python 3 標準ライブラリのみ ・ **ネットワーク呼出なし（全ローカル）**

---

## こんな手作業を、消す

不動産の現場では、同じ概念が会社・ポータル・担当者ごとにバラバラの言葉で書かれます
（`マイソク` / `物件概要書` / `販売図面`、`さんため` / `三為`、`築15年` / `平成23年築`）。
人手でやっていた整形・台帳化・用語確認を、内蔵辞書と正規化ハーネスで機械処理します。

| 現場の手作業 | fudosan-ontology で |
|---|---|
| 物確メモの表記ゆれを手で直す | 住所・面積・築年・方位を**自動で統一表記**に |
| 反響メールの希望条件を手で台帳化 | 賃料 / 間取り / エリア / 設備を**自動タグ化** |
| 広告・物件文から条件を拾う | ペット / 楽器 / 民泊 等を条件タグに（可否は要確認に倒す） |
| 「マイソク」「三為」…略語が新人に伝わらない | 用語 → 正規形 + やさしい定義を**即引き** |
| OCR / CSV の表記バラつきを名寄せ | **2,400+ エイリアス**で正規形へ寄せる |
| AI が業者語を理解しない | **MCP** で AI に辞書 + 正規化を渡す |

すべて**全ローカル・ネットワーク呼出なし・MIT**。現場のデータを外に出さずに使えます。

---

## クイックスタート

### AI から使う（MCP・インストール不要）

お使いの AI クライアントの設定に 1 行追加するだけ。Claude Code / Claude Desktop /
OpenAI Codex / Cline / Cursor など MCP 対応クライアントで動きます。

**npx（Node）**
```json
{ "mcpServers": { "fudosan-ontology": { "command": "npx", "args": ["-y", "fudosan-ontology", "serve"] } } }
```

**uvx（Python）**
```json
{ "mcpServers": { "fudosan-ontology": { "command": "uvx", "args": ["fudosan-ontology", "serve"] } } }
```

クライアントを選んで自動設定する**導入ウィザード**（ローカル LLM を選ぶと搭載メモリを見て推奨モデルを提示）：

```bash
npx -y fudosan-ontology init       # または: uvx fudosan-ontology init
npx -y fudosan-ontology selftest   # 動作確認
```

### 開発・ローカルで使う（clone）

```bash
git clone https://github.com/shoeiiwaya/fudosan-ontology.git
cd fudosan-ontology
python3 -m fudosan_ontology.ontology --selftest-gate
```

期待される出力:

```
✓ selftest pass (MT-006/033/068/301/302/305 gates fired)
```

依存ゼロ（Python 3 標準ライブラリのみ）。インストール不要・ネットワーク不要。

### 用語を名寄せする（Python）

```python
from fudosan_ontology import ontology as O
onto = O.load_ontology()

term = onto["alias_to_term"][O.norm_key("さんため")]
print(term)                                      # => 三為（さんため）
print(onto["term_to_entry"][term]["category"])   # => baibai
```

### 自由文を標準形に落とす（ハーネス）

```bash
python3 -m fudosan_ontology.ontology --make-template     # 記入用 input_template.csv を生成
python3 -m fudosan_ontology.ontology sample_terms.csv    # 入力CSVを処理 → out/ に成果物
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

### 🤖 MCP サーバ
- `resolve_term` — 用語 → 正規形 + 定義 + カテゴリ + 同義語 + 英訳 + 法令出典
- `normalize` — 自由文 → 標準タグ・正規化値（ハーネスと同一ロジック・**uvx 版**）
- `assess_risk` — 住所 → 災害/ハザード語彙（外部リスク評価 API 接続はスタブ）
- 改行区切り JSON-RPC・依存ゼロ・ネットワーク呼出なし
- 配布: **npx**（Node, `resolve_term` / `assess_risk`）と **uvx**（Python, 全ツール）。`normalize` は npx 版に順次対応。

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

## MCP 登録の詳細

設定スニペットは上記[クイックスタート](#クイックスタート)（npx / uvx の 1 行）を参照。
`npx -y fudosan-ontology init`（または `uvx fudosan-ontology init`）でクライアントを選んで自動設定もできます。

clone して直接動かす場合（開発）:

```bash
python3 -m fudosan_ontology.mcp_server   # MCP サーバを起動（stdin/stdout）
python3 -m unittest discover -s tests    # 全テスト（ハーネス + MCP）
node test/test_node.js                   # Node 版 MCP のテスト
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
3. `python3 -m fudosan_ontology.ontology --selftest-gate` と `python3 -m unittest discover -s tests` が緑であることを確認
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
