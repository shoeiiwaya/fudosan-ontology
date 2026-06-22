"use strict";
// Python ハーネスと JS 移植の出力一致を機械保証する parity test。
// 同じ入力を Python process() と JS process() に通し、構造化出力をデータ比較する。
// （structured/attrs は JSON 文字列なのでパースして比較＝整形差を無視しデータで判定）
const path = require("path");
const { execFileSync } = require("child_process");
const { process: jsProcess } = require("../src/normalize");

const ROOT = path.join(__dirname, "..");
const PY = `import sys, json
from fudosan_ontology import ontology as O
rows = json.load(sys.stdin)
onto = O.load_ontology()
out = [O.process([r], onto) for r in rows]
print(json.dumps(out, ensure_ascii=False))`;

const INPUTS = [
  { row_id: "A1", kind: "address", text: "東京都千代田区霞が関一丁目２番３号" },
  { row_id: "A2", kind: "address", text: "中央区銀座二十三丁目五番" },
  { row_id: "A3", kind: "address", text: "○○市大字田中字山1234番地2" },
  { row_id: "A4", kind: "address", text: "町名1-2" },
  { row_id: "R1", kind: "requirement", text: "中野区か杉並区で2LDKを探してます。家賃15万円以内、駅徒歩10分以内、ペット可で。40㎡以上希望" },
  { row_id: "R2", kind: "requirement", text: "バス・トイレ別 オートロック 宅配ボックス 南向き 独立洗面台 1Kでも可" },
  { row_id: "P1", kind: "property", text: "専有48.6㎡、平成20年築、南東向き、ペット相談可、民泊相談可、オートロック" },
  { row_id: "P2", kind: "property", text: "25坪 築15年 北西向き 楽器不可 事務所利用可" },
  { row_id: "P3", kind: "property", text: "駐車場あり、オートロック、宅配ボックス、独立洗面台、床暖房、追い焚き、角部屋、最上階、システムキッチン、食器洗い乾燥機、ペット相談可、民泊相談可" },
  { row_id: "T1", kind: "term", text: "三為で取得した物件、ナゾノゴをフガフガする、特約を確認" },
  { row_id: "X1", kind: "foobar", text: "未知の種別" },
];

function pyOutputs() {
  const raw = execFileSync("python3", ["-c", PY], {
    input: JSON.stringify(INPUTS),
    cwd: ROOT,
    env: Object.assign({}, process.env, { PYTHONPATH: ROOT, RI_HUB_NO_ENV_FILE: "1" }),
    maxBuffer: 64 * 1024 * 1024,
  });
  return JSON.parse(raw.toString());
}

// structured/attrs の JSON 文字列をパースして正規化（整形差を吸収）
function norm(state) {
  const c = JSON.parse(JSON.stringify(state));
  (c.requirements || []).forEach((r) => { if (typeof r.structured === "string") r.structured = JSON.parse(r.structured); });
  (c.attrs || []).forEach((a) => { if (typeof a.attrs === "string") a.attrs = JSON.parse(a.attrs); });
  return c;
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

let pass = 0, fail = 0;
const py = pyOutputs();
INPUTS.forEach((row, i) => {
  const expected = norm(py[i]);
  const actual = norm(jsProcess([row]));
  if (eq(actual, expected)) { pass++; console.log("ok   - parity", row.row_id, `(${row.kind})`); }
  else {
    fail++;
    console.error("FAIL - parity", row.row_id, `(${row.kind})`);
    console.error("  py:", JSON.stringify(expected));
    console.error("  js:", JSON.stringify(actual));
  }
});
console.log(`\n${pass} passed, ${fail} failed (Python↔JS process parity)`);
process.exit(fail ? 1 : 0);
