"use strict";
// fudosan-ontology Node パッケージの実テスト（ゼロ依存・node:assert のみ）。
const path = require("path");
const { spawn } = require("child_process");
const { handle } = require("../src/server");
const { resolveTerm, assessRisk } = require("../src/resolve");

let pass = 0;
let fail = 0;
function ok(name, cond) {
  if (cond) { pass++; console.log("ok   -", name); }
  else { fail++; console.error("FAIL -", name); }
}

// --- resolve（Python版との一致を実値で確認） ---
let r = resolveTerm("さんため");
ok("resolve さんため -> 三為（括弧読み併記の名寄せ）", r.matched && r.term.indexOf("三為") === 0);
r = resolveTerm("ハザードマップ");
ok("resolve ハザードマップ matched + category=chousa", r.matched && r.term === "ハザードマップ" && r.category === "chousa");
r = resolveTerm("マイソク");
ok("resolve マイソク matched", r.matched && r.term === "マイソク");
r = resolveTerm("ナゾノゴ");
ok("resolve 未収録 -> matched=false", r.matched === false && r.term === null);

// --- assess_risk スタブ ---
const a = assessRisk("千代田区霞が関1-2-3");
ok("assess connected=false / risk_score=null", a.connected === false && a.risk_score === null);
ok("assess hazard_vocabulary に ハザードマップ", a.hazard_vocabulary.length > 0 && a.hazard_vocabulary.includes("ハザードマップ"));

// --- protocol handle() ---
const init = handle({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} });
ok("initialize serverInfo.name=fudosan-ontology", init.result.serverInfo.name === "fudosan-ontology");
const list = handle({ jsonrpc: "2.0", id: 2, method: "tools/list" });
ok("tools/list = resolve_term+assess_risk", list.result.tools.map((t) => t.name).sort().join(",") === "assess_risk,resolve_term");
const call = handle({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "resolve_term", arguments: { term: "レインズ" } } });
const payload = JSON.parse(call.result.content[0].text);
ok("tools/call resolve_term レインズ", payload.matched && payload.term === "レインズ");
const bad = handle({ jsonrpc: "2.0", id: 4, method: "tools/call", params: { name: "nope", arguments: {} } });
ok("未知 tool は isError", bad.result.isError === true);
const notif = handle({ jsonrpc: "2.0", method: "notifications/initialized" });
ok("notifications は応答なし(null)", notif === null);

// --- 実 stdio サブプロセス（改行区切り JSON-RPC） ---
const bin = path.join(__dirname, "..", "bin", "fudosan-ontology.js");
const p = spawn(process.execPath, [bin, "serve"]);
let buf = "";
p.stdout.on("data", (d) => (buf += d.toString()));
p.on("close", () => {
  const lines = buf.trim().split("\n").filter(Boolean).map((l) => JSON.parse(l));
  ok("stdio: 2 応答", lines.length === 2);
  ok("stdio initialize", lines[0] && lines[0].result && lines[0].result.serverInfo.name === "fudosan-ontology");
  const pl = JSON.parse(lines[1].result.content[0].text);
  ok("stdio resolve_term さんため", pl.matched && pl.term.indexOf("三為") === 0);
  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
});
p.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} }) + "\n");
p.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "resolve_term", arguments: { term: "さんため" } } }) + "\n");
p.stdin.end();
