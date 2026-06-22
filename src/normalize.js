"use strict";
// Python ハーネス(ontology.py)の忠実移植。出力は Python 版 process() と一致(parity test で担保)。
const fs = require("fs");
const path = require("path");
const { normKey } = require("./resolve");

const DATA = path.join(__dirname, "..", "data");
let _alias = null;
let _known = null;
function loadIndex() {
  if (_alias) return;
  _alias = JSON.parse(fs.readFileSync(path.join(DATA, "alias_index.json"), "utf8"));
  _known = JSON.parse(fs.readFileSync(path.join(DATA, "known_surfaces.json"), "utf8"));
}

const KINDS = new Set(["address", "requirement", "property", "advert", "term"]);
const round2 = (x) => Math.round(x * 100) / 100;
// Python str(float) 互換: 整数値は "N.0"（例 float("15")→"15.0"）。表示文字列の一致用。
const pyFloat = (x) => (Number.isInteger(x) ? x.toFixed(1) : String(x));
// Python json.dumps(ensure_ascii=False) 既定セパレータ(", " / ": ")を再現
function pyDumps(v) {
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return "[" + v.map(pyDumps).join(", ") + "]";
  if (typeof v === "object") {
    return "{" + Object.entries(v).map(([k, val]) => JSON.stringify(k) + ": " + pyDumps(val)).join(", ") + "}";
  }
  if (typeof v === "string") return JSON.stringify(v);
  return String(v);
}

// ---- MT-301 住所正規化 / MT-302 判別 ----
const KANJI_DIGIT = { "〇": "0", "零": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9" };
const KANJI_UNIT = { "十": 10, "百": 100, "千": 1000 };

function kanjiSeqToInt(seq) {
  if (!seq) return null;
  let total = 0, current = 0, hasUnit = false;
  for (const ch of seq) {
    if (ch in KANJI_DIGIT) {
      const d = parseInt(KANJI_DIGIT[ch], 10);
      current = (current && ch !== "〇" && ch !== "零") ? current * 10 + d : d;
    } else if (ch in KANJI_UNIT) {
      hasUnit = true;
      total += (current || 1) * KANJI_UNIT[ch];
      current = 0;
    } else return null;
  }
  total += current;
  if (total === 0 && !hasUnit && seq !== "〇" && seq !== "零") return null;
  return total;
}
const kanjiRepl = (m) => { const v = kanjiSeqToInt(m); return v != null ? String(v) : m; };

function normalizeAddress(raw) {
  const notes = [];
  const base = (raw || "").normalize("NFKC").trim();
  let s = base.replace(/[ \t]+/g, "");
  s = s.replace(/[〇零一二三四五六七八九十百千]+(?=丁目|丁|番地|番|号|の|-|−|ー|―)/g, kanjiRepl);
  s = s.replace(/(?<=[町村大字])[〇零一二三四五六七八九十百千]+/g, kanjiRepl);
  s = s.replace(/(\d+)丁目/g, "$1-");
  s = s.replace(/(\d+)番地の?(\d+)/g, "$1-$2");
  s = s.replace(/(\d+)番地/g, "$1-");
  s = s.replace(/(\d+)番(\d+)号/g, "$1-$2");
  s = s.replace(/(\d+)番(?!地)/g, "$1-");
  s = s.replace(/(\d+)号(?!室|棟|館)/g, "$1");
  s = s.replace(/(\d+)の(\d+)/g, "$1-$2");
  s = s.replace(/[−ー―‐－]/g, "-");
  s = s.replace(/-{2,}/g, "-");
  s = s.replace(/-+$/g, "");
  if (s !== base) notes.push("丁目番号/全角/漢数字を正規化");
  return { normalized: s, notes };
}

function classifyAddressType(rawNormalized, rawOriginal) {
  const orig = (rawOriginal || "").normalize("NFKC");
  const s = rawNormalized;
  const hasChome = orig.includes("丁目");
  const hasGo = /\d+号(?!室|棟|館)/.test(orig);
  const hasBanchi = orig.includes("番地");
  const hasAza = orig.includes("大字") || /字[^\d]/.test(orig);
  if (hasAza) return { type: "地番", confidence: "high", gate: "OK", reason: "「大字」「字」を含む＝地番系" };
  if (hasChome) {
    if (hasGo) return { type: "住居表示", confidence: "high", gate: "OK", reason: "丁目+番+号の3階層＝住居表示の典型" };
    return { type: "住居表示", confidence: "medium", gate: "OK", reason: "「丁目」を含む（市街地の住居表示系・号は未確認）" };
  }
  if (hasGo) return { type: "住居表示", confidence: "medium", gate: "OK", reason: "「号」を含む＝住居表示の可能性が高い" };
  if (hasBanchi) return { type: "地番", confidence: "medium", gate: "OK", reason: "「番地」を含み丁目/号が無い＝地番系の可能性" };
  if (/\d+-\d+/.test(s)) return { type: "不明", confidence: "low", gate: "Approval", reason: "丁目/番地/号の語が無く地番か住居表示か断定不可（要確認）" };
  return { type: "不明", confidence: "low", gate: "Approval", reason: "住所の番号体系を特定できず断定不可（要確認）" };
}

// ---- MT-006 希望条件 ----
const REQ_FACILITY_TAGS = {
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
};

function tagRequirements(text) {
  const nk = normKey(text);
  const tags = [];
  const structured = {};
  let m = text.replace(/ＬＤＫ/g, "LDK").match(/(?<![0-9A-Za-z])(\d)\s*([SLDK]{1,4})(?![A-Za-z])/i);
  if (m) { structured.layout = `${m[1]}${m[2].toUpperCase()}`; tags.push(`間取り:${structured.layout}`); }
  m = text.match(/(?:家賃|賃料|予算)?\s*([0-9]+(?:\.[0-9]+)?)\s*(万|万円)/);
  if (m) { const man = parseFloat(m[1]); structured.rent_max_yen = Math.round(man * 10000); tags.push(`賃料上限:${pyFloat(man)}万円`); }
  m = text.match(/(?:駅\s*)?(?:徒歩)?\s*([0-9]+)\s*分(?:以内|まで)?/);
  if (m) { structured.walk_max_min = parseInt(m[1], 10); tags.push(`駅徒歩以内:${m[1]}分`); }
  m = text.match(/([0-9]+(?:\.[0-9]+)?)\s*(㎡|平米|m2|平方メートル|帖|畳|坪)(?:以上)?/);
  if (m) { structured.area_min_raw = `${m[1]}${m[2]}`; tags.push(`面積以上:${m[1]}${m[2]}`); }
  for (const [tag, aliases] of Object.entries(REQ_FACILITY_TAGS)) {
    if (aliases.some((a) => nk.includes(normKey(a)))) tags.push(tag);
  }
  for (const seg of text.split(/[、，,・\/\sかとやのまたは及び又は]+/)) {
    for (const mm of seg.matchAll(/([一-龥ァ-ヶー]{1,8}(?:区|市|町|村|駅))/g)) {
      tags.push(`エリア:${mm[1]}`); (structured.areas || (structured.areas = [])).push(mm[1]);
    }
    for (const mm of seg.matchAll(/([一-龥ァ-ヶー]{1,8}線)/g)) {
      tags.push(`エリア:${mm[1]}`); (structured.areas || (structured.areas = [])).push(mm[1]);
    }
  }
  return { tags: [...new Set(tags)].sort(), structured };
}

// ---- MT-033 物件/広告 条件 ----
const CONDITION_RULES = [
  ["ペット", "ペット可", "ペット不可", ["ペット可", "ペット相談", "ペットOK", "犬可", "猫可", "ペット飼育可"], ["ペット不可", "ペット禁止", "ペットNG"], false],
  ["楽器", "楽器可", "楽器不可", ["楽器可", "楽器相談", "演奏可", "ピアノ可", "防音室"], ["楽器不可", "楽器禁止", "演奏不可"], false],
  ["民泊", "民泊可（要確認）", "民泊不可", ["民泊可", "民泊相談", "住宅宿泊事業可", "Airbnb可", "民泊運用可"], ["民泊不可", "民泊禁止", "住宅宿泊事業不可", "AirbnbNG"], true],
  ["事務所利用", "事務所利用可", "事務所利用不可", ["事務所可", "事務所利用可", "SOHO可", "SOHO相談", "店舗事務所可", "事業利用可"], ["事務所不可", "住居専用", "事業利用不可"], false],
  ["法人契約", "法人契約可", "法人契約不可", ["法人契約可", "法人可"], ["法人契約不可", "法人不可"], false],
];

function tagConditions(text) {
  const nk = normKey(text);
  const tags = [];
  const needsConfirm = [];
  for (const [label, okTag, ngTag, okAliases, ngAliases, confirm] of CONDITION_RULES) {
    const ngHit = ngAliases.some((a) => nk.includes(normKey(a)));
    const okHit = okAliases.some((a) => nk.includes(normKey(a)));
    if (ngHit) tags.push(ngTag);
    else if (okHit) {
      tags.push(okTag);
      if (confirm) needsConfirm.push(`${label}: 広告は可だが運用可否は法令/管理規約/条例で要確認（180日上限等）`);
    }
  }
  return { tags: [...new Set(tags)].sort(), needs_confirm: needsConfirm };
}

// ---- MT-068 面積・築年・方位 ----
const TSUBO_TO_SQM = 3.305785;
const JO_SQM = 1.62;
const DIRECTION_KANJI_NORM = { "南東": "南東", "東南": "南東", "南西": "南西", "西南": "南西", "北東": "北東", "東北": "北東", "北西": "北西", "西北": "北西", "南": "南", "北": "北", "東": "東", "西": "西" };
const DIRECTION_LATIN = [["南東", "se"], ["南西", "sw"], ["北東", "ne"], ["北西", "nw"], ["南", "s"], ["北", "n"], ["東", "e"], ["西", "w"]];
const DIRECTION_CTX_RE = /([南北東西]{1,2})\s*(?:向き|向|面し?た?|採光|方角|バルコニー|ベランダ|開口)/;
const DIRECTION_LABEL_RE = /(?:向き|方位|方角|採光|開口部?|バルコニー|ベランダ|主?居室|主?寝室|リビング|窓)\s*(?:は|が|の)?\s*[:：=＝]?\s*([南北東西]{1,2})(?![京阪神駅口区市町村])/;
const DIRECTION_LATIN_RE = /(?<![a-z])(se|sw|ne|nw|[nsew])(?![a-z])/;
const ERA_BASE = { "令和": 2018, "平成": 1988, "昭和": 1925 };
const ERA_RE = /(令和|平成|昭和)\s*(\d+|元)\s*年/;
const AREA_RE = /([0-9]+(?:\.[0-9]+)?)\s*(㎡|平米|m2|平方メートル|坪|帖|畳)/;
const CHIKU_YEAR_RE = /築\s*([0-9]+)\s*年/;
const SEIREKI_RE = /(?:19|20)([0-9]{2})\s*年(?:築|竣工|新築)?/;

function normalizeAttrs(text, thisYear = 2026) {
  const out = {};
  const notes = [];
  let m = text.match(AREA_RE);
  if (m) {
    const val = parseFloat(m[1]);
    const unit = m[2].normalize("NFKC");
    let sqm, src;
    if (["㎡", "平米", "m2", "平方メートル"].includes(unit)) { sqm = val; src = `${pyFloat(val)}㎡`; }
    else if (unit === "坪") { sqm = round2(val * TSUBO_TO_SQM); src = `${pyFloat(val)}坪`; }
    else { sqm = round2(val * JO_SQM); src = `${pyFloat(val)}帖`; }
    out.area_sqm = sqm;
    out.area_tsubo = round2(sqm / TSUBO_TO_SQM);
    out.area_source = src;
    notes.push(`面積統一: ${src}→${pyFloat(sqm)}㎡`);
  }
  let seireki = null;
  m = text.normalize("NFKC").match(ERA_RE);
  if (m) {
    const n = m[2] === "元" ? 1 : parseInt(m[2], 10);
    seireki = ERA_BASE[m[1]] + n;
    notes.push(`和暦→西暦: ${m[1]}${m[2]}年→${seireki}年`);
  }
  if (seireki === null) {
    const ms = text.match(SEIREKI_RE);
    if (ms) seireki = parseInt(ms[0].slice(0, 4), 10);
  }
  const chiku = text.match(CHIKU_YEAR_RE);
  if (seireki !== null) {
    out.built_year = seireki;
    out.building_age = Math.max(0, thisYear - seireki);
    notes.push(`築年: ${seireki}年築(築${out.building_age}年/基準${thisYear})`);
  } else if (chiku) {
    const age = parseInt(chiku[1], 10);
    out.building_age = age;
    out.built_year = thisYear - age;
    notes.push(`築年: 築${age}年→推定${out.built_year}年(基準${thisYear})`);
  }
  const nfkc = text.normalize("NFKC");
  let rawDir = null;
  const mctx = nfkc.match(DIRECTION_CTX_RE) || nfkc.match(DIRECTION_LABEL_RE);
  if (mctx) rawDir = mctx[1];
  if (rawDir) {
    const normed = DIRECTION_KANJI_NORM[rawDir] || DIRECTION_KANJI_NORM[rawDir.slice(-1)];
    if (normed) { out.direction = normed; notes.push(`方位統一: ${normed}向き`); }
  } else {
    const mlat = nfkc.toLowerCase().match(DIRECTION_LATIN_RE);
    if (mlat) {
      for (const [normed, alias] of DIRECTION_LATIN) {
        if (mlat[1] === alias) { out.direction = normed; notes.push(`方位統一: ${normed}向き（英字${mlat[1].toUpperCase()}）`); break; }
      }
    }
  }
  return { attrs: out, notes };
}

// ---- MT-305 新語提案 ----
const STOPWORDS = new Set(["こと", "もの", "ため", "など", "それ", "これ", "あれ", "どれ", "場合", "とき", "ところ", "ください", "します", "しました", "ました", "して", "され", "される", "できる", "できます", "です", "ます", "ある", "あり", "なる", "なり", "そして", "また", "ただし", "なお", "および", "確認", "連絡", "対応", "案内", "相談", "希望", "検討", "予定", "可能", "不可", "本日", "本件", "本物件", "当該", "当社", "弊社", "御社", "貴社", "業者", "担当", "顧客", "先方", "今回", "今後", "段取", "段取り", "手配", "準備", "実施", "完了", "開始", "終了", "以上", "以下", "未満", "程度", "取得", "取引", "売買", "賃貸", "物件", "情報", "内容", "書類", "資料", "金額", "費用", "価格", "契約", "締結", "解除", "説明", "報告", "提出", "送付", "返送", "記載", "確定", "変更", "修正"]);
const TOKEN_RE = /[一-龥々]{2,}|[ァ-ヶー]{3,}|[A-Za-z]{3,}/g;

function isKnownFragment(tok) {
  const nk = normKey(tok);
  if (nk.length < 2) return false;
  for (const surf of _known) {
    const ns = normKey(surf);
    if (ns.length < 2) continue;
    if (nk.includes(ns) || ns.includes(nk)) return true;
  }
  return false;
}

function proposeNewTerms(text) {
  loadIndex();
  const proposals = [];
  const seen = new Set();
  for (const mm of text.matchAll(TOKEN_RE)) {
    const tok = mm[0];
    if (STOPWORDS.has(tok) || seen.has(tok)) continue;
    seen.add(tok);
    if (normKey(tok) in _alias) continue;
    if (isKnownFragment(tok)) continue;
    const kind = /[一-龥々]/.test(tok[0]) ? "kanji" : (/[ァ-ヶー]/.test(tok[0]) ? "katakana" : "latin");
    proposals.push({ candidate: tok, kind, gate: "Hold", reason: "辞書未収録。新語として追加するか人間が判断（同義語化/別概念/誤抽出）" });
  }
  return proposals;
}

// ---- process（Python process() と同一構造・audit 含む） ----
function process(rows, thisYear = 2026) {
  loadIndex();
  const addresses = [], requirements = [], conditions = [], attrs = [], proposals = [], audit = [], holds = [];
  let seq = 0;
  const addAudit = (action, target, gate_status, detail) => {
    seq += 1;
    const e = { audit_id: `ONT-AUD-${String(seq).padStart(4, "0")}`, timestamp: `seq:${String(seq).padStart(4, "0")}`, actor: "fudosan-ontology", action, target, gate_status };
    Object.assign(e, detail || {});
    audit.push(e);
  };
  for (const row of rows) {
    const rid = row.row_id, kind = row.kind, text = row.text;
    if (!KINDS.has(kind)) { addAudit("skip_unknown_kind", rid, "Block", { note: `未知の種別: ${kind}` }); continue; }
    if (kind === "address") {
      const { normalized, notes } = normalizeAddress(text);
      const c = classifyAddressType(normalized, text);
      addresses.push({ row_id: rid, normalized, address_type: c.type, confidence: c.confidence, gate: c.gate, reason: c.reason, notes: notes.join("; ") });
      addAudit("address_normalize_classify", `${rid}/<addr:masked>`, c.gate, { address_type: c.type, confidence: c.confidence });
      if (c.gate === "Approval") holds.push(`[${rid}] 住所の地番/住居表示が断定不可（要確認）: ${normalized}`);
    } else if (kind === "requirement") {
      const res = tagRequirements(text);
      requirements.push({ row_id: rid, tags: res.tags.join(" / "), structured: pyDumps(res.structured) });
      addAudit("requirement_tagging", rid, "OK", { tag_count: res.tags.length });
    } else if (kind === "property" || kind === "advert") {
      const cres = tagConditions(text);
      const ares = normalizeAttrs(text, thisYear);
      conditions.push({ row_id: rid, kind, condition_tags: cres.tags.join(" / "), needs_confirm: cres.needs_confirm.join(" | ") });
      attrs.push({ row_id: rid, kind, attrs: pyDumps(ares.attrs), notes: ares.notes.join("; ") });
      const gate = cres.needs_confirm.length ? "Approval" : "OK";
      addAudit("condition_attr_tagging", rid, gate, { condition_count: cres.tags.length });
      for (const c of cres.needs_confirm) holds.push(`[${rid}] ${c}`);
    } else if (kind === "term") {
      const props = proposeNewTerms(text);
      for (const p of props) {
        proposals.push(Object.assign({}, p, { row_id: rid }));
        addAudit("new_term_proposal", `${rid}/${p.candidate}`, "Hold", { candidate: p.candidate });
        holds.push(`[${rid}] 新語提案『${p.candidate}』→ 辞書追加可否を人間判断(Hold)`);
      }
      if (!props.length) addAudit("new_term_proposal", rid, "OK", { note: "未知語なし" });
    }
  }
  return { addresses, requirements, conditions, attrs, proposals, holds, audit };
}

module.exports = {
  KINDS, process, normalizeAddress, classifyAddressType, tagRequirements,
  tagConditions, normalizeAttrs, proposeNewTerms, kanjiSeqToInt,
};
