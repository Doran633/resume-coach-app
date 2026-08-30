import type { GenerateResponse, GenerationTaskResponse, Identity } from "../types/api";

const jsonHeaders = { "Content-Type": "application/json" };
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const generationTimeoutMs = 15 * 60 * 1000;
let identityBootstrap: Promise<void> | undefined;

async function ensureServerIdentity() {
  if (!identityBootstrap) {
    identityBootstrap = fetch(buildApiUrl("/api/identity"), {
      method: "POST",
      credentials: "include"
    }).then((response) => {
      if (!response.ok) throw new Error("identity bootstrap failed");
    }).catch((error) => {
      identityBootstrap = undefined;
      throw error;
    });
  }
  return identityBootstrap;
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly code?: string,
    public readonly retryAfter?: number
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export function buildApiUrl(path: string) {
  return `${apiBaseUrl}${path}`;
}

export async function trackEvent(identity: Identity, event_name: string, payload: Record<string, any> = {}) {
  await ensureServerIdentity().catch(() => undefined);
  await fetch(buildApiUrl("/api/events"), {
    method: "POST",
    headers: jsonHeaders,
    credentials: "include",
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
    attempt_id?: string;
  },
  onStatus?: (status: GenerationTaskResponse) => void
): Promise<GenerateResponse> {
  await ensureServerIdentity();
  let task = await requestJson<GenerationTaskResponse>("/api/generation-attempts", {
      method: "POST",
      headers: jsonHeaders,
      credentials: "include",
      body: JSON.stringify({ ...identity, ...payload }),
    });
  return pollGenerationTask(task, onStatus);
}

async function pollGenerationTask(
  initialTask: GenerationTaskResponse,
  onStatus?: (status: GenerationTaskResponse) => void
): Promise<GenerateResponse> {
  const startedAt = Date.now();
  let task = initialTask;
  onStatus?.(task);
  while (Date.now() - startedAt < generationTimeoutMs) {
    if (task.status === "succeeded" && task.generation) return task.generation;
    if (task.status === "failed" || task.status === "expired") {
      throw new ApiRequestError(task.user_message || "generation failed", undefined, task.error_code);
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    task = await requestJson<GenerationTaskResponse>(`/api/generation-attempts/${encodeURIComponent(task.attempt_id)}`, {
      method: "GET",
      credentials: "include"
    });
    onStatus?.(task);
  }
  throw new ApiRequestError("generation timeout", undefined, "MODEL_TIMEOUT");
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildApiUrl(path), init);
  } catch {
    throw new ApiRequestError("network request failed", undefined, "network");
  }
  if (!response.ok) {
    let message = "request failed";
    let errorCode: string | undefined;
    let retryAfter: number | undefined;
    try {
      const body = await response.json();
      const detail = body?.detail ?? body;
      message = detail?.user_message ?? detail?.message ?? message;
      errorCode = detail?.error_code;
      retryAfter = detail?.retry_after;
    } catch {
      message = await response.text().catch(() => message);
    }
    throw new ApiRequestError(message, response.status, errorCode, retryAfter);
  }
  return response.json() as Promise<T>;
}

export async function createDocx(identity: Identity, generation_result_id: number) {
  try {
    await ensureServerIdentity();
    const response = await fetch(buildApiUrl("/api/resume/docx"), {
      method: "POST",
      headers: jsonHeaders,
      credentials: "include",
      body: JSON.stringify({ ...identity, generation_result_id, version_type: "recommended" })
    });
    if (!response.ok) throw new ApiRequestError(await response.text(), response.status);
    return response.json() as Promise<{ file_id: number; file_name: string; download_url: string }>;
  } catch (error) {
    if (error instanceof ApiRequestError) throw error;
    throw new ApiRequestError("network request failed", undefined, "network");
  }
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
  try {
    await ensureServerIdentity();
    const response = await fetch(buildApiUrl("/api/feedback"), {
      method: "POST",
      headers: jsonHeaders,
      credentials: "include",
      body: JSON.stringify({ ...identity, ...payload })
    });
    if (!response.ok) throw new ApiRequestError(await response.text(), response.status);
    return response.json();
  } catch (error) {
    if (error instanceof ApiRequestError) throw error;
    throw new ApiRequestError("network request failed", undefined, "network");
  }
}

export async function deleteMyData() {
  await ensureServerIdentity();
  return requestJson<{ ok: boolean; files_cleanup_pending: number }>("/api/privacy/my-data", {
    method: "DELETE",
    credentials: "include"
  });
}
