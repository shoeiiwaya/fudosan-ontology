"use strict";
// 導入ウィザード: クライアントを選ぶ → MCP 設定を出力／書き込み。
// ローカルLLM を選んだ場合は RAM を見て推奨モデルを提示（ゼロ依存・Node 標準のみ）。
const os = require("os");
const fs = require("fs");
const path = require("path");
const readline = require("readline");
const { spawnSync } = require("child_process");

const SERVER_ENTRY = { command: "npx", args: ["-y", "fudosan-ontology", "serve"] };
const MCP_JSON = { mcpServers: { "fudosan-ontology": SERVER_ENTRY } };

// 設定ファイルにマージ書き込みするクライアント（ファイルパスを返す）
function clientConfigPath(client) {
  const home = os.homedir();
  if (client === "claude-desktop") {
    if (process.platform === "darwin") return path.join(home, "Library", "Application Support", "Claude", "claude_desktop_config.json");
    if (process.platform === "win32") return path.join(process.env.APPDATA || path.join(home, "AppData", "Roaming"), "Claude", "claude_desktop_config.json");
    return path.join(home, ".config", "Claude", "claude_desktop_config.json");
  }
  if (client === "cursor") return path.join(home, ".cursor", "mcp.json");
  return null;
}

// 既存の mcpServers と他キーを保全したままマージ。書き込み前にバックアップ。
function mergeMcpFile(file) {
  let cfg = {};
  let backedUp = null;
  if (fs.existsSync(file)) {
    try { cfg = JSON.parse(fs.readFileSync(file, "utf8")) || {}; } catch (e) { cfg = {}; }
    backedUp = `${file}.bak-${new Date().toISOString().replace(/[:.]/g, "-")}`;
    fs.copyFileSync(file, backedUp);
  } else {
    fs.mkdirSync(path.dirname(file), { recursive: true });
  }
  if (!cfg.mcpServers || typeof cfg.mcpServers !== "object") cfg.mcpServers = {};
  cfg.mcpServers["fudosan-ontology"] = SERVER_ENTRY;
  fs.writeFileSync(file, JSON.stringify(cfg, null, 2) + "\n");
  return { file, backedUp };
}

// クライアントへ自動導入。claude-code は CLI、desktop/cursor はファイルマージ、他は手順表示。
function installClient(client) {
  const out = process.stdout;
  if (client === "claude-code") {
    const r = spawnSync("claude", ["mcp", "add", "-s", "user", "fudosan-ontology", "--", "npx", "-y", "fudosan-ontology", "serve"], { encoding: "utf8" });
    if (r.status === 0) { out.write("✓ Claude Code に登録しました。新しいセッションで有効になります。\n"); return 0; }
    out.write("Claude Code CLI が見つかりませんでした。次を実行してください:\n\n  claude mcp add -s user fudosan-ontology -- npx -y fudosan-ontology serve\n");
    return 1;
  }
  const file = clientConfigPath(client);
  if (file) {
    try {
      const r = mergeMcpFile(file);
      out.write(`✓ 設定を書き込みました: ${r.file}\n`);
      if (r.backedUp) out.write(`  （元の設定は ${r.backedUp} にバックアップ）\n`);
      out.write("  クライアントを再起動すると fudosan-ontology が使えます。\n");
      return 0;
    } catch (e) {
      out.write(`自動書き込みに失敗: ${e.message}\n\n手動設定:\n${(CLIENTS[client] || {}).how ? CLIENTS[client].how() : ""}\n`);
      return 1;
    }
  }
  out.write(`${(CLIENTS[client] || {}).how ? CLIENTS[client].how() : `不明なクライアント: ${client}`}\n`);
  return 0;
}

const CLIENTS = {
  "claude-code": {
    label: "Claude Code (CLI)",
    how: () =>
      "ターミナルで次を実行:\n\n  claude mcp add fudosan-ontology -- npx -y fudosan-ontology serve\n",
  },
  "claude-desktop": {
    label: "Claude Desktop",
    how: () => {
      const p =
        process.platform === "darwin"
          ? "~/Library/Application Support/Claude/claude_desktop_config.json"
          : process.platform === "win32"
          ? "%APPDATA%\\Claude\\claude_desktop_config.json"
          : "~/.config/Claude/claude_desktop_config.json";
      return `設定ファイル ${p} の "mcpServers" に追記:\n\n${JSON.stringify(MCP_JSON, null, 2)}`;
    },
  },
  codex: {
    label: "OpenAI Codex CLI",
    how: () =>
      "~/.codex/config.toml に追記:\n\n" +
      '[mcp_servers.fudosan-ontology]\ncommand = "npx"\nargs = ["-y", "fudosan-ontology", "serve"]\n',
  },
  cline: {
    label: "Cline (VS Code)",
    how: () =>
      'Cline の MCP 設定 (cline_mcp_settings.json) の "mcpServers" に追記:\n\n' +
      JSON.stringify(MCP_JSON, null, 2),
  },
  cursor: {
    label: "Cursor",
    how: () => `~/.cursor/mcp.json に追記:\n\n${JSON.stringify(MCP_JSON, null, 2)}`,
  },
  generic: {
    label: "その他 / 汎用 MCP クライアント",
    how: () =>
      "MCP 設定の mcpServers に次を追記（多くのクライアントで共通）:\n\n" +
      JSON.stringify(MCP_JSON, null, 2),
  },
  "local-llm": {
    label: "ローカル LLM で使う（モデル推奨つき）",
    how: () => localLlmGuide(),
  },
};

function recommendModel() {
  const gb = Math.round(os.totalmem() / 1024 ** 3);
  let tier;
  if (gb < 8) {
    tier = {
      warn: true,
      models: ["Llama 3.2 3B (Q4)", "Qwen2.5 3B (Q4)", "Gemma 2 2B"],
      note: "RAM が少なめ。3〜4B 級の量子化(Q4)を推奨。重いタスクは厳しい。",
    };
  } else if (gb < 16) {
    tier = { models: ["Qwen2.5 7B (Q4)", "Llama 3.1 8B (Q4)", "Gemma 2 9B (Q4)"], note: "7〜8B 級(Q4)が快適。" };
  } else if (gb < 32) {
    tier = { models: ["Qwen2.5 14B (Q4)", "Phi-4 14B (Q4)", "Llama 3.1 8B (fp16)"], note: "13〜14B 級(Q4)まで実用的。" };
  } else if (gb < 64) {
    tier = { models: ["Qwen2.5 32B (Q4)", "Gemma 2 27B (Q4)"], note: "30B 級(Q4)が狙える。" };
  } else {
    tier = { models: ["Llama 3.3 70B (Q4)", "Qwen2.5 72B (Q4)"], note: "70B 級(Q4)も可。" };
  }
  return Object.assign({ ram_gb: gb }, tier);
}

function localLlmGuide() {
  const r = recommendModel();
  const lines = [];
  lines.push(`検出した搭載メモリ: 約 ${r.ram_gb} GB`);
  if (r.warn) lines.push("⚠️ メモリに余裕が少なめです。小さめモデル＋量子化を推奨します。");
  lines.push("");
  lines.push(`推奨モデル目安: ${r.models.join(" / ")}`);
  lines.push(`  ${r.note}`);
  lines.push("  日本語の不動産文には日本語が強いモデル(Qwen 系 / Sakana 系 / ELYZA 系)が好相性。");
  lines.push("  ※ GPU 搭載機は VRAM 基準で。最新の入手可否は各ランナー(Ollama / LM Studio 等)で確認を。");
  lines.push("");
  lines.push("ローカル LLM ランナー側で本 MCP サーバ(`npx -y fudosan-ontology serve`)をツールとして登録すると、");
  lines.push("選んだローカルモデルが不動産用語の名寄せを呼べます。設定形式は各ランナーの MCP 対応に従ってください。");
  return lines.join("\n");
}

function printConfig(client) {
  const c = CLIENTS[client];
  if (!c) {
    process.stdout.write(
      `不明なクライアント: ${client}\n利用可能: ${Object.keys(CLIENTS).join(", ")}\n`
    );
    process.exitCode = 1;
    return;
  }
  process.stdout.write(`\n# ${c.label}\n\n${c.how()}\n`);
}

function help() {
  process.stdout.write(
    [
      "fudosan-ontology — 不動産 業界用語・名寄せオントロジー (MCP)",
      "",
      "使い方:",
      "  npx -y fudosan-ontology serve     MCP サーバを起動 (クライアントが起動)",
      "  npx -y fudosan-ontology init      導入ウィザード (クライアントを選んで設定)",
      "  npx -y fudosan-ontology install <client>  指定クライアントへ設定を自動書き込み",
      "  npx -y fudosan-ontology config <client>   指定クライアントの設定を表示",
      "",
      "  <client> = " + Object.keys(CLIENTS).join(" | "),
      "",
    ].join("\n")
  );
}

function runWizard() {
  const keys = Object.keys(CLIENTS);
  const out = process.stdout;
  out.write("\nfudosan-ontology 導入ウィザード\n使うツールを選んでください:\n\n");
  keys.forEach((k, i) => out.write(`  ${i + 1}) ${CLIENTS[k].label}\n`));
  out.write("\n番号を入力 (Enter で 1): ");

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  rl.once("line", (line) => {
    const n = parseInt(String(line).trim(), 10);
    const idx = Number.isInteger(n) && n >= 1 && n <= keys.length ? n - 1 : 0;
    const key = keys[idx];
    const canWrite = key === "claude-desktop" || key === "cursor" || key === "claude-code";
    if (!canWrite) {
      out.write(`\n# ${CLIENTS[key].label}\n\n${CLIENTS[key].how()}\n`);
      rl.close();
      return;
    }
    out.write(`\n# ${CLIENTS[key].label}\n設定を自動で書き込みますか？（バックアップを取ってから追記します） (Y/n): `);
    rl.once("line", (ans) => {
      out.write("\n");
      if (/^n/i.test(String(ans).trim())) out.write(`${CLIENTS[key].how()}\n`);
      else installClient(key);
      rl.close();
    });
  });
}

module.exports = { printConfig, runWizard, help, recommendModel, installClient, clientConfigPath, mergeMcpFile, CLIENTS };
