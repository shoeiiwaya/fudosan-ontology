"use strict";
// 名寄せの核。辞書(ontology.json)と Python 生成の alias_index.json を読み、
// Python 版 norm_key と同一規則で照合する（resolve 結果の Python/JS 完全一致を担保）。
const fs = require("fs");
const path = require("path");

const DATA = path.join(__dirname, "..", "data");

let _onto = null;
let _alias = null;
let _byTerm = null;

function load() {
  if (_onto) return;
  _onto = JSON.parse(fs.readFileSync(path.join(DATA, "ontology.json"), "utf8"));
  _alias = JSON.parse(fs.readFileSync(path.join(DATA, "alias_index.json"), "utf8"));
  _byTerm = Object.create(null);
  for (const e of _onto.entries) _byTerm[e.term] = e;
}

// Python ontology.norm_key と同一: NFKC → 小文字 → 空白/中黒/括弧/句読点除去
function normKey(s) {
  return (s || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\s・･（）()【】[\]「」、,，。．]/g, "");
}

function meta() {
  load();
  return {
    name: _onto.name,
    version: _onto.version,
    term_count: _onto.term_count,
    license: _onto.license,
    disclaimer: _onto.disclaimer,
  };
}

function resolveTerm(input) {
  load();
  const term = input == null ? "" : String(input).trim();
  if (!term) throw new Error("term が必要です");
  const matched = _alias[normKey(term)];
  if (matched) {
    const e = _byTerm[matched] || {};
    return {
      tool: "resolve_term",
      input: term,
      matched: true,
      term: matched,
      reading: e.reading || "",
      category: e.category || "",
      synonyms: e.synonyms || [],
      definition_pro: e.definition_pro || "",
      definition_plain: e.definition_plain || "",
      english: e.english || "",
      legal_source: e.legal_source == null ? null : e.legal_source,
      related_terms: e.related_terms || [],
      caution: e.caution == null ? null : e.caution,
    };
  }
  return {
    tool: "resolve_term",
    input: term,
    matched: false,
    term: null,
    note: "辞書未収録。新語提案(Hold)は完全版ハーネス(Python / uvx 版)で扱います。",
    new_term_proposals: [],
  };
}

const HAZARD_KEYWORDS = [
  "ハザード", "浸水", "洪水", "土砂", "液状化", "津波", "地震", "高潮",
  "内水", "河川", "災害", "防災", "警戒区域", "レッドゾーン", "イエローゾーン",
];

function hazardVocabulary() {
  load();
  const out = new Set();
  for (const e of _onto.entries) {
    const blob = [
      e.term || "",
      e.definition_pro || "",
      e.definition_plain || "",
      (e.synonyms || []).join(" "),
    ].join(" ");
    if (HAZARD_KEYWORDS.some((k) => blob.includes(k))) out.add(e.term);
  }
  return [...out].sort();
}

function assessRisk(input) {
  const address = input == null ? "" : String(input).trim();
  if (!address) throw new Error("address が必要です");
  return {
    tool: "assess_risk",
    input: address,
    normalized_address: null,
    risk_score: null,
    connected: false,
    note:
      "リスクスコア接続スタブ。本パッケージはネットワーク呼出を行いません。" +
      "住所正規化は完全版(Python / uvx 版)が行います。外部リスク評価 API への接続は別レイヤー(docs/RISK_BRIDGE.md)。",
    hazard_vocabulary: hazardVocabulary(),
  };
}

module.exports = { normKey, resolveTerm, assessRisk, hazardVocabulary, meta };
