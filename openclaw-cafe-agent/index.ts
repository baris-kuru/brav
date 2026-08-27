import { existsSync, readFileSync } from "fs";

import { BACKEND_URL, ok, readJson } from "./shared";

const cafePlugin = {
  id: "openclaw-cafe-agent",
  name: "brav",
  description: "Cafe operations, receipt ingestion, stock, staffing and manager insights",

  register(api: any) {
    api.registerTool({
      name: "cafe_manager",
      label: "Cafe Manager",
      description: "Manage cafe operations, receipts, stock, staffing and analytics. Actions: dashboard, operations, load_cafe_data, recent_batches, find_receipts, merchant_spend, ask_analysis, ask_manager, ingest_paths.",
      parameters: {
        type: "object",
        properties: {
          action: { type: "string" },
          args: { type: "object" },
        },
        required: ["action"],
      },
      execute: async (_id: string, params: any) => {
        const action = String(params.action || "");
        const args = params.args ?? {};

        if (action === "dashboard") {
          const data = await readJson<any>(`${BACKEND_URL}/api/dashboard`);
          return ok(`Dashboard\n\n${data.story}`);
        }

        if (action === "operations") {
          const data = await readJson<any>(`${BACKEND_URL}/api/operations`);
          return ok(JSON.stringify(data, null, 2));
        }

        if (action === "load_cafe_data") {
          const data = await readJson<any>(`${BACKEND_URL}/api/data/seed`, { method: "POST" });
          return ok(JSON.stringify(data.seeded, null, 2));
        }

        if (action === "recent_batches") {
          const data = await readJson<any>(`${BACKEND_URL}/api/batches?limit=${args.limit ?? 10}`);
          return ok(JSON.stringify(data.batches, null, 2));
        }

        if (action === "find_receipts") {
          const merchant = args.merchant ? `&merchant=${encodeURIComponent(String(args.merchant))}` : "";
          const limit = Number(args.limit ?? 25);
          const data = await readJson<any>(`${BACKEND_URL}/api/receipts?limit=${limit}${merchant}`);
          return ok(JSON.stringify(data.receipts, null, 2));
        }

        if (action === "merchant_spend") {
          if (!args.merchant_name) return ok("merchant_spend requires args.merchant_name");
          const data = await readJson<any>(`${BACKEND_URL}/api/merchants/${encodeURIComponent(String(args.merchant_name))}`);
          return ok(JSON.stringify(data, null, 2));
        }

        if (action === "ask_analysis") {
          if (!args.question) return ok("ask_analysis requires args.question");
          const data = await readJson<any>(`${BACKEND_URL}/api/analysis/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: args.question }),
          });
          return ok(String(data.answer || ""));
        }

        if (action === "ask_manager") {
          if (!args.question) return ok("ask_manager requires args.question");
          const data = await readJson<any>(`${BACKEND_URL}/api/manager/ask`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: args.question }),
          });
          return ok(String(data.answer || ""));
        }

        if (action === "ingest_paths") {
          const paths = Array.isArray(args.paths) ? args.paths : [];
          if (!paths.length) return ok("ingest_paths requires args.paths");
          const form = new FormData();
          for (const filePath of paths) {
            if (!existsSync(filePath)) return ok(`File not found: ${filePath}`);
            const blob = new Blob([readFileSync(filePath)], { type: "application/pdf" });
            form.append("files", blob, String(filePath).split("/").pop() || "receipt.pdf");
          }
          const batchName = args.batch_name ? `?batch_name=${encodeURIComponent(String(args.batch_name))}` : "";
          const response = await fetch(`${BACKEND_URL}/api/receipts/ingest${batchName}`, {
            method: "POST",
            body: form,
          });
          if (!response.ok) {
            return ok(`Ingest failed: ${response.status} ${await response.text()}`);
          }
          return ok(JSON.stringify(await response.json(), null, 2));
        }

        return ok(`Unknown cafe_manager action: ${action}`);
      },
    } as any);
  },
};

export default cafePlugin;
