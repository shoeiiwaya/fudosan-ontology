🌐 [日本語](README.md) | **English**

# fudosan-ontology

> ### ▶️ **[Try it in 30 seconds](#quick-start)** · [browse the dictionary](ontology.md) 👈

An open **workflow tool** that lets AI read messy Japanese real-estate text — property notes,
inquiries, listing copy, OCR data — **in the trade's own jargon and normalize it**. It resolves
spelling variants, abbreviations, and inconsistent addresses / areas / build-years. Ships a
built-in **377-term dictionary** and a local **MCP server** so AI (e.g. Claude) can call it directly.

**v1** · MIT License · Python 3 standard library only · **No network access (fully local)**

---

## Manual work it removes

In Japanese real estate, the same concept is written differently by every company, portal,
and agent (`マイソク` / `物件概要書` / `販売図面`; `さんため` / `三為`; `築15年` / `平成23年築`).
The clean-up, logging, and term-lookup people used to do by hand is handled by the built-in
dictionary and the normalization harness.

| Manual work | With fudosan-ontology |
|---|---|
| Fixing spelling variants in property notes by hand | Auto-normalize address / area / build-year / direction |
| Logging inquiry requirements by hand | Auto-tag rent / layout / area / amenities |
| Pulling conditions out of listing copy | Pets / instruments / minpaku → condition tags (permissibility → review) |
| Jargon like "マイソク" / "三為" new hires don't know | Term → canonical + plain definition, instantly |
| Name-matching messy OCR / CSV | Resolve to canonical via **2,400+ aliases** |
| AI doesn't understand the trade's jargon | Hand the dictionary + normalization to AI over **MCP** |

All **fully local, no network, MIT** — your data never leaves the machine.

---

## Quick start

### Use from AI (MCP, no install)

Add one line to your AI client's config. Works with Claude Code, Claude Desktop,
OpenAI Codex, Cline, Cursor, and other MCP clients.

**npx (Node)**
```json
{ "mcpServers": { "fudosan-ontology": { "command": "npx", "args": ["-y", "fudosan-ontology", "serve"] } } }
```

**uvx (Python)**
```json
{ "mcpServers": { "fudosan-ontology": { "command": "uvx", "args": ["fudosan-ontology", "serve"] } } }
```

Or run the setup wizard to pick a client and write the config (for local LLMs it inspects RAM and recommends a model):

```bash
npx -y fudosan-ontology init       # or: uvx fudosan-ontology init
npx -y fudosan-ontology selftest   # smoke check
```

### Develop / run locally (clone)

```bash
git clone https://github.com/shoeiiwaya/fudosan-ontology.git
cd fudosan-ontology
python3 -m fudosan_ontology.ontology --selftest-gate
```

Expected output:

```
✓ selftest pass (MT-006/033/068/301/302/305 gates fired)
```

Zero dependencies (Python 3 standard library only). No install, no network.

### Resolve a term (Python)

```python
from fudosan_ontology import ontology as O
onto = O.load_ontology()

term = onto["alias_to_term"][O.norm_key("さんため")]
print(term)                                      # => 三為（さんため）
print(onto["term_to_entry"][term]["category"])   # => baibai
```

### Normalize free text (harness)

```bash
python3 -m fudosan_ontology.ontology --make-template     # generate an input template CSV
python3 -m fudosan_ontology.ontology sample_terms.csv    # process input CSV → artifacts in out/
```

---

## Features

### 📖 Dictionary (`ontology.json`)
- **377 terms / 10 domains** — sales, leasing, listing/ads, registry, due diligence, contracts,
  investment, ryokan/lodging, finance, field slang
- **2,400+ aliases** — kanji/kana/romaji, full/half-width, okurigana, abbreviations → canonical form
- **Bilingual** — pro definition `definition_pro` / plain definition `definition_plain` / `english`
- **Statute references** — `legal_source` reference pointers (→ [Disclaimer](#legal-disclaimer-important))

### 🔤 Name-matching & normalization harness (`ontology.py`)
- **Address normalization** (MT-301) — full-width/kanji digits/chome-ban-go → half-width hyphens
- **Chiban vs. residential-display detection** (MT-302) — ambiguous → review gate
- **Requirement tagging** (MT-006) — rent / layout / walk-time / area / amenities / region
- **Condition tagging** (MT-033) — pets/instruments/minpaku; permissibility is never asserted (review)
- **Area / age / direction normalization** (MT-068) — tsubo/jo→㎡, wareki/seireki/age, 8 directions
- **New-term proposals** (MT-305) — adding to the dictionary is a human decision (Hold)

### 🤖 MCP server (`mcp_server.py`)
- `resolve_term` — term → canonical + definition + category + synonyms + english + statute
- `normalize` — free text → standard tags / normalized values (same logic as the harness)
- `assess_risk` — address → disaster/hazard vocabulary (external risk API connection is a stub)
- Newline-delimited JSON-RPC, zero dependencies, no network
- Distribution: both **npx** (Node) and **uvx** (Python) expose all tools (`resolve_term` / `normalize` / `assess_risk`); outputs are verified identical by a Python↔JS parity test.

### 🛡️ Design promises
- Never **asserts** law, permissibility, or money (uncertain → review / `null`)
- Addresses are PII → masked in audit logs
- Never fabricates sources; states a clear disclaimer (→ [Disclaimer](#legal-disclaimer-important))

---

## Architecture

```
field free text ──▶ [ ontology.py harness ] ──▶ standard tags / normalized values / audit log
                            ▲
                    [ ontology.json dictionary ]
                    377 terms / 2,400+ aliases / 10 domains
                            ▲
              [ mcp_server.py ]  ⇄  Claude and other AI / MCP clients
```

Everything is Python standard library only, fully local, with no network access.

---

## MCP registration (Claude Code / Claude Desktop, etc.)

```json
{
  "mcpServers": {
    "fudosan-ontology": { "command": "npx", "args": ["-y", "fudosan-ontology", "serve"] }
  }
}
```

```bash
python3 -m fudosan_ontology.mcp_server   # start from a clone (stdin/stdout)
python3 -m unittest discover -s tests    # all tests (harness + MCP)
```

---

## Documentation

- [SPEC.md](SPEC.md) — harness spec, capability matrix, gate definitions
- [docs/RISK_BRIDGE.md](docs/RISK_BRIDGE.md) — bridging the hazard vocabulary to an external risk API
- [docs/verification-log.md](docs/verification-log.md) — record of verified statutes and constants
- [MANIFESTO.md](MANIFESTO.md) — why this is free and open

---

## Contributing

1. Add/edit entries in `domains/<key>.json`
2. Run `python3 build.py` to merge and detect collisions
3. Confirm `python3 -m fudosan_ontology.ontology --selftest-gate` and `python3 -m unittest discover -s tests` are green
4. Open a Pull Request

**Adding new synonyms and spelling variants grows the dictionary fastest.** Issues / PRs welcome.

---

## Legal disclaimer (important)

The definitions (`definition_pro` / `definition_plain`) and statute references (`legal_source`)
in this dictionary are **reference information**, **not legal advice**.

- `legal_source` values are **reference pointers** whose existence was checked at build time
  (Civil Code, Building Standards Act, Real Property Registration Act, Real Estate Brokerage Act,
  Land/Building Lease Act, City Planning Act, etc.; ~200 entries). They **do not guarantee the
  latest article numbers, amendments, or interpretation.**
- Before any use with legal effect — important-matters explanation, contracts, filings, taxes —
  **always verify against the current statutory text and consult a professional** (lawyer, tax
  accountant, licensed real estate transaction agent, etc.).
- The harness relies on statute logic at runtime in only 2 places, both independently re-verified
  ([docs/verification-log.md](docs/verification-log.md)). Entry-level `legal_source` is separate
  reference metadata.

The authors accept no liability for any outcome of using this dictionary (MIT, "AS IS").

---

## License

[MIT License](LICENSE) — Copyright (c) 2026 株式会社理 (Kotowari Inc.)

---

> **fudosan-ontology** by [@shoeiiwaya](https://github.com/shoeiiwaya) — the open vocabulary layer for Japanese real estate.
