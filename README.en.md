🌐 [日本語](README.md) | **English**

# fudosan-ontology

> ### ▶️ **[Browse the 377-term dictionary](ontology.md)** 👈

An open vocabulary dictionary that resolves the **industry terms, spelling variants, and
abbreviations** of Japanese real estate (the licensed brokerage trade) into a
machine-usable canonical form. **377 terms / 10 domains / 2,400+ aliases.**
Ships with an **MCP server** so AI can query it in natural language.

**v1** · MIT License · Python 3 standard library only · **No network access (fully local)**

---

## Why fudosan-ontology?

In Japanese real estate, the same concept is written differently by every company, portal,
and agent (`マイソク` / `物件概要書` / `販売図面`; `さんため` / `三為`; `築15年` / `平成23年築`).
Because no standardized shared vocabulary exists as a public good, every team rebuilds its own
name-matching dictionary for AI, OCR, and data integration. This makes it **one open dictionary**.

| | Roll your own | Closed in-house dict | **fudosan-ontology** |
|---|:---:|:---:|:---:|
| 377 terms / 10 domains | each time | scattered | **✅** |
| Alias / variant resolution | DIY | internal only | **✅ 2,400+ aliases** |
| Callable from AI (MCP) | ❌ | ❌ | **✅ included** |
| Self-host · PII stays local | – | – | **✅ no network** |
| Statute references | each time | unknown | **✅ reference pointers** |
| Cost | engineering | license fees | **¥0** |
| Source code | – | closed | **MIT (this repo)** |

---

## Quick start

### Try it in 30 seconds

```bash
git clone https://github.com/shoeiiwaya/fudosan-ontology.git
cd fudosan-ontology
python3 ontology.py --selftest-gate
```

Expected output:

```
✓ selftest pass (MT-006/033/068/301/302/305 gates fired)
```

Zero dependencies (Python 3 standard library only). No install, no network.

### Resolve a term (Python)

```python
import ontology as O
onto = O.load_ontology()

term = onto["alias_to_term"][O.norm_key("さんため")]
print(term)                                      # => 三為（さんため）
print(onto["term_to_entry"][term]["category"])   # => baibai
```

### Normalize free text (harness)

```bash
python3 ontology.py --make-template     # generate an input template CSV
python3 ontology.py sample_terms.csv    # process input CSV → artifacts in out/
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
- Newline-delimited JSON-RPC, standard library only, no network

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
    "fudosan-ontology": { "command": "python3", "args": ["/abs/path/to/fudosan-ontology/mcp_server.py"] }
  }
}
```

```bash
python3 mcp_server.py     # connect to an MCP client over stdin/stdout
python3 test_mcp.py       # verify real tool calls
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
3. Confirm `python3 ontology.py --selftest-gate` and `python3 test_ontology.py` are green
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
