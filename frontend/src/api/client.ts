import type { GenerateResponse, Identity } from "../types/api";

const jsonHeaders = { "Content-Type": "application/json" };
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const generationTimeoutMs = 45000;

export function buildApiUrl(path: string) {
  return `${apiBaseUrl}${path}`;
}

export async function trackEvent(identity: Identity, event_name: string, payload: Record<string, any> = {}) {
  await fetch(buildApiUrl("/api/events"), {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ ...identity, event_name, payload })
  }).catch(() => undefined);
}

export async function generateExperience(
  identity: Identity,
  payload: {
    target_role: string;
    mode: string;
    packaging_level: string;
    experience_type: string;
    raw_input: string;
  }
): Promise<GenerateResponse> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), generationTimeoutMs);
  const response = await fetch(buildApiUrl("/api/generate"), {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ ...identity, ...payload }),
    signal: controller.signal
  }).catch((error) => {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("模型生成超时，请检查 API 配置或先切回 mock 模式测试。");
    }
    throw error;
  });
  window.clearTimeout(timeoutId);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function createDocx(identity: Identity, generation_result_id: number) {
  const response = await fetch(buildApiUrl("/api/resume/docx"), {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ ...identity, generation_result_id, version_type: "recommended" })
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<{ file_id: number; file_name: string; download_url: string }>;
}

export async function submitFeedback(
  identity: Identity,
  payload: {
    generation_result_id?: number;
    model_comparison: string;
    value_choice: string;
    comment?: string;
  }
) {
  const response = await fetch(buildApiUrl("/api/feedback"), {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ ...identity, ...payload })
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
