import { existsSync, readFileSync } from "fs";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT_DIR = resolve(__dirname, "..");

function readEnvValue(key: string): string {
  const envPaths = [
    join(ROOT_DIR, ".env"),
    join(ROOT_DIR, "..", "HomeAssistant", ".env"),
  ];
  for (const path of envPaths) {
    if (!existsSync(path)) continue;
    const match = readFileSync(path, "utf8").match(new RegExp(`^${key}=(.*)$`, "m"));
    if (match?.[1]?.trim()) return match[1].trim();
  }
  return "";
}

export const BACKEND_URL = process.env.CAFE_BACKEND_URL?.trim() || readEnvValue("CAFE_BACKEND_URL") || "http://127.0.0.1:8010";

export function ok(text: string) {
  return { content: [{ type: "text" as const, text }] };
}

export async function readJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return await response.json() as T;
}
