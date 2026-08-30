import { ApiRequestError } from "../api/client";

export type GenerationErrorType = "timeout" | "network" | "server" | "configuration" | "invalid_response" | "rate_limit" | "capacity" | "input" | "budget" | "unknown";

export type GenerationErrorInfo = {
  type: GenerationErrorType;
  message: string;
};

export function getGenerationErrorInfo(error: unknown): GenerationErrorInfo {
  if (error instanceof ApiRequestError) {
    if (error.code === "timeout" || error.code === "MODEL_TIMEOUT") {
      return { type: "timeout", message: "生成时间超过预期，请稍后重试。您的输入内容仍然保留。" };
    }
    if (error.code === "INPUT_TOO_LARGE") return { type: "input", message: error.message };
    if (error.code === "USER_RATE_LIMITED" || error.code === "IP_RATE_LIMITED") {
      return { type: "rate_limit", message: error.message || "操作有些频繁，请稍后再试。" };
    }
    if (
      error.code === "GENERATION_QUEUE_FULL"
      || error.code === "GENERATION_ALREADY_RUNNING"
      || error.code === "PROTECTION_DEGRADED"
    ) {
      return { type: "capacity", message: error.message || "当前生成任务较多，请稍后再试。" };
    }
    if (error.code === "GENERATION_EXPIRED") {
      return { type: "timeout", message: "生成任务等待时间过长，请重新提交。您的输入内容仍然保留。" };
    }
    if (error.code === "DAILY_BUDGET_REACHED") {
      return { type: "budget", message: "今日生成容量已达到上限，请稍后再试。您的输入内容仍然保留。" };
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

export function getOperationErrorMessage(error: unknown, operation: "docx" | "feedback") {
  const info = getGenerationErrorInfo(error);
  if (operation === "docx") {
    if (info.type === "network") return "暂时无法连接文件服务，请检查网络后重试。当前简历结果仍然保留。";
    if (info.type === "configuration") return "文件服务配置异常，请联系网站维护者。";
    return "暂时无法生成 DOCX，请稍后重试。当前简历结果仍然保留。";
  }
  if (info.type === "network") return "暂时无法提交评价，请检查网络后重试。您填写的内容仍然保留。";
  return "评价暂时没有提交成功，请稍后重试。您填写的内容仍然保留。";
}
