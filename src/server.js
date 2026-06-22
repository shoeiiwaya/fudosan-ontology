"use strict";
// fudosan-ontology MCP server (Node・ゼロ依存)。
// MCP 標準の stdio transport = 改行区切り JSON（1メッセージ1行）。
const readline = require("readline");
const { resolveTerm, assessRisk } = require("./resolve");
const { process: runProcess, KINDS } = require("./normalize");

const PROTOCOL_VERSION = "2024-11-05";
const SERVER_INFO = { name: "fudosan-ontology", version: "0.1.0" };

const TOOLS = [
  {
    name: "resolve_term",
    description:
      "不動産の業界用語・表記ゆれ・略語を正規形へ名寄せし、定義・カテゴリ・同義語・英訳・法令出典を返す。",
    inputSchema: {
      type: "object",
      properties: { term: { type: "string", description: "名寄せしたい用語・表記ゆれ・略語" } },
      required: ["term"],
      additionalProperties: false,
    },
  },
  {
    name: "assess_risk",
    description:
      "住所に対し辞書由来の災害/ハザード語彙を返す。実リスクスコア取得は行わない（接続スタブ・ネットワークなし）。",
    inputSchema: {
      type: "object",
      properties: { address: { type: "string", description: "住所" } },
      required: ["address"],
      additionalProperties: false,
    },
  },
  {
    name: "normalize",
    description:
      "現場の自由文（住所/希望条件/物件文/広告文/用語）を標準タグ・正規化値に落とす。ハーネスと同一ロジック。",
    inputSchema: {
      type: "object",
      properties: {
        kind: { type: "string", enum: ["address", "requirement", "property", "advert", "term"], description: "入力種別" },
        text: { type: "string", description: "自由文" },
      },
      required: ["kind", "text"],
      additionalProperties: false,
    },
  },
];

function normalizeTool(a) {
  const kind = String(a.kind || "").trim();
  const text = String(a.text != null ? a.text : "").trim();
  if (!KINDS.has(kind)) throw new Error(`kind は ${[...KINDS].join(", ")} のいずれかです`);
  if (!text) throw new Error("text が必要です");
  const st = runProcess([{ row_id: "MCP-001", kind, text, memo: "" }]);
  return {
    tool: "normalize", kind, input: text,
    addresses: st.addresses, requirements: st.requirements, conditions: st.conditions,
    attrs: st.attrs, new_term_proposals: st.proposals, holds: st.holds,
    gates: st.audit.map((e) => e.gate_status),
  };
}

const HANDLERS = {
  resolve_term: (a) => resolveTerm(a.term != null ? a.term : a.text),
  normalize: normalizeTool,
  assess_risk: (a) => assessRisk(a.address != null ? a.address : a.text),
};

function contentResult(payload, isError) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
    isError: !!isError,
  };
}

function handle(msg) {
  const method = msg.method;
  const id = msg.id;
  const params = msg.params || {};

  if (method && method.indexOf("notifications/") === 0) return null;

  try {
    let result;
    if (method === "initialize") {
      result = {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: { tools: { listChanged: false } },
        serverInfo: SERVER_INFO,
        instructions:
          "fudosan-ontology 名寄せ辞書 MCP。resolve_term / assess_risk。全ローカル・ネットワーク呼出なし。法令・可否・金額は確定しない。",
      };
    } else if (method === "ping") {
      result = {};
    } else if (method === "tools/list") {
      result = { tools: TOOLS };
    } else if (method === "tools/call") {
      const name = params.name;
      const args = params.arguments || {};
      if (!HANDLERS[name]) {
        result = contentResult({ error: `未知の tool: ${name}` }, true);
      } else {
        try {
          result = contentResult(HANDLERS[name](args));
        } catch (e) {
          result = contentResult(
            { status: "ERROR", tool: name, error: String((e && e.message) || e), error_type: e && e.name },
            true
          );
        }
      }
    } else {
      return { jsonrpc: "2.0", id, error: { code: -32601, message: `Method not found: ${method}` } };
    }
    return { jsonrpc: "2.0", id, result };
  } catch (e) {
    return { jsonrpc: "2.0", id, error: { code: -32603, message: String((e && e.message) || e) } };
  }
}

function serve() {
  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  rl.on("line", (line) => {
    const s = line.trim();
    if (!s) return;
    let msg;
    try {
      msg = JSON.parse(s);
    } catch (e) {
      return;
    }
    const resp = handle(msg);
    if (resp !== null) process.stdout.write(JSON.stringify(resp) + "\n");
  });
  rl.on("close", () => process.exit(0));
}

module.exports = { serve, handle, TOOLS, SERVER_INFO, PROTOCOL_VERSION };
