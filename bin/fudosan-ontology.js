#!/usr/bin/env node
"use strict";
// MCP クライアントが起動した時(stdin が piped)はサーバ。
// 人が端末で叩いた時(TTY)は導入ウィザード。明示は serve / init / config。
const arg = process.argv[2];

if (arg === "serve") {
  require("../src/server").serve();
} else if (arg === "init" || arg === "setup") {
  require("../src/wizard").runWizard();
} else if (arg === "config") {
  require("../src/wizard").printConfig(process.argv[3]);
} else if (arg === "selftest") {
  const { resolveTerm, meta } = require("../src/resolve");
  const r = resolveTerm("マイソク");
  const m = meta();
  if (r.matched && r.term === "マイソク") {
    console.log(`✓ selftest pass (辞書 ${m.term_count} 語ロード OK / 名寄せ OK)`);
  } else {
    console.error("✗ selftest FAIL");
    process.exitCode = 1;
  }
} else if (arg === "-v" || arg === "--version") {
  process.stdout.write(require("../package.json").version + "\n");
} else if (arg === "-h" || arg === "--help" || arg === "help") {
  require("../src/wizard").help();
} else if (!arg) {
  if (process.stdin.isTTY) require("../src/wizard").runWizard();
  else require("../src/server").serve();
} else {
  require("../src/wizard").help();
  process.exitCode = 1;
}
