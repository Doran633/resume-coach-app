import type { GenerateResponse, GenerationTaskResponse, Identity } from "../types/api";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";
const generationTimeoutMs = 15 * 60 * 1000;
let identityBootstrap: Promise<void> | undefined;

export type ApiResult<T> = { data: T; requestId?: string };
export type GeneratedExperience = { generation: GenerateResponse; requestId?: string };

export function createRequestId() {
  const suffix = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID().replace(/-/g, "")
    : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 14)}`;
  return `req_${suffix}`;
}

function headersWithRequestId(init: RequestInit, requestId: string) {
  const headers = new Headers(init.headers);
  headers.set("X-Request-ID", requestId);
  return headers;
}

async function ensureServerIdentity() {
  if (!identityBootstrap) {
    const requestId = createRequestId();
    identityBootstrap = fetch(buildApiUrl("/api/identity"), {
      method: "POST",
      credentials: "include",
      headers: { "X-Request-ID": requestId }
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
    public readonly retryAfter?: number,
    public readonly requestId?: string
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
  const requestId = createRequestId();
  await fetch(buildApiUrl("/api/events"), {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Request-ID": requestId },
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
): Promise<GeneratedExperience> {
  await ensureServerIdentity();
  const initial = await requestJson<GenerationTaskResponse>("/api/generation-attempts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ ...identity, ...payload }),
  }, createRequestId());
  return pollGenerationTask(initial.data, onStatus, initial.requestId);
}

async function pollGenerationTask(
  initialTask: GenerationTaskResponse,
  onStatus?: (status: GenerationTaskResponse) => void,
  supportRequestId?: string
): Promise<GeneratedExperience> {
  const startedAt = Date.now();
  let task = initialTask;
  onStatus?.(task);
  while (Date.now() - startedAt < generationTimeoutMs) {
    if (task.status === "succeeded" && task.generation) {
      return { generation: task.generation, requestId: supportRequestId };
    }
    if (task.status === "failed" || task.status === "expired") {
      throw new ApiRequestError(
        task.user_message || "generation failed", undefined, task.error_code,
        undefined, supportRequestId
      );
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    const polled = await requestJson<GenerationTaskResponse>(
      `/api/generation-attempts/${encodeURIComponent(task.attempt_id)}`,
      { method: "GET", credentials: "include" }
    );
    task = polled.data;
    onStatus?.(task);
  }
  throw new ApiRequestError("generation timeout", undefined, "MODEL_TIMEOUT", undefined, supportRequestId);
}

async function requestJson<T>(path: string, init: RequestInit, requestedId = createRequestId()): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(buildApiUrl(path), {
      ...init,
      headers: headersWithRequestId(init, requestedId)
    });
  } catch {
    throw new ApiRequestError("network request failed", undefined, "network");
  }
  const requestId = response.headers.get("X-Request-ID") || undefined;
  if (!response.ok) {
    let message = "request failed";
    let errorCode: string | undefined;
    let retryAfter: number | undefined;
    try {
      const body = await response.clone().json();
      const detail = body?.detail ?? body;
      message = detail?.user_message ?? detail?.message ?? message;
      errorCode = detail?.error_code;
      retryAfter = detail?.retry_after;
    } catch {
      message = await response.text().catch(() => message);
    }
    throw new ApiRequestError(message, response.status, errorCode, retryAfter, requestId);
  }
  return { data: await response.json() as T, requestId };
}

export async function createDocx(identity: Identity, generation_result_id: number) {
  await ensureServerIdentity();
  const result = await requestJson<{ file_id: number; file_name: string; download_url: string }>(
    "/api/resume/docx",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ ...identity, generation_result_id, version_type: "recommended" })
    }
  );
  return { ...result.data, support_request_id: result.requestId };
}

export async function downloadDocx(downloadUrl: string) {
  let response: Response;
  try {
    response = await fetch(buildApiUrl(downloadUrl), {
      method: "GET",
      credentials: "include",
      headers: { "X-Request-ID": createRequestId() }
    });
  } catch {
    throw new ApiRequestError("network request failed", undefined, "network");
  }
  const requestId = response.headers.get("X-Request-ID") || undefined;
  if (!response.ok) {
    throw new ApiRequestError("download failed", response.status, "DOWNLOAD_FAILED", undefined, requestId);
  }
  return { blob: await response.blob(), requestId };
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
  await ensureServerIdentity();
  const result = await requestJson<{ ok: boolean; feedback_id: number }>("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ ...identity, ...payload })
  });
  return { ...result.data, support_request_id: result.requestId };
}

export async function deleteMyData() {
  await ensureServerIdentity();
  const result = await requestJson<{ ok: boolean; files_cleanup_pending: number }>("/api/privacy/my-data", {
    method: "DELETE",
    credentials: "include"
  });
  return { ...result.data, support_request_id: result.requestId };
}
