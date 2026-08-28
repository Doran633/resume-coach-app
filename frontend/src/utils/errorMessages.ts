import { ApiRequestError } from "../api/client";

export type GenerationErrorType = "timeout" | "network" | "server" | "configuration" | "invalid_response" | "unknown";

export type GenerationErrorInfo = {
  type: GenerationErrorType;
  message: string;
};

export function getGenerationErrorInfo(error: unknown): GenerationErrorInfo {
  if (error instanceof ApiRequestError) {
    if (error.code === "timeout") {
      return { type: "timeout", message: "生成时间超过预期，请稍后重试。您的输入内容仍然保留。" };
    }
    if (error.status === 401 || error.status === 403) {
      return { type: "configuration", message: "生成服务配置异常，请联系网站维护者。" };
    }
    if (error.status && error.status >= 500) {
      return { type: "server", message: "生成服务暂时出现问题，请稍后重新尝试。" };
    }
    if (error.code === "network") {
      return { type: "network", message: "暂时无法连接生成服务，请检查网络后重试。您的输入内容不会丢失。" };
    }
  }

  const rawMessage = error instanceof Error ? error.message : String(error);
  if (/json|parse|schema|validation|字段|结构|不完整/i.test(rawMessage)) {
    return { type: "invalid_response", message: "本次生成结果不完整，请重新生成一次。" };
  }
  if (/timeout|timed out|超时|abort/i.test(rawMessage)) {
    return { type: "timeout", message: "生成时间超过预期，请稍后重试。您的输入内容仍然保留。" };
  }
  if (/failed to fetch|network|网络|连接/i.test(rawMessage)) {
    return { type: "network", message: "暂时无法连接生成服务，请检查网络后重试。您的输入内容不会丢失。" };
  }
  return { type: "unknown", message: "本次生成没有成功，请稍后重试。您的输入内容仍然保留。" };
}
