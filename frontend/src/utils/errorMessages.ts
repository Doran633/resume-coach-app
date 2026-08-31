import { ApiRequestError } from "../api/client";

export type GenerationErrorType = "timeout" | "network" | "server" | "configuration" | "invalid_response" | "rate_limit" | "capacity" | "input" | "budget" | "unknown";

export type GenerationErrorInfo = {
  type: GenerationErrorType;
  message: string;
  requestId?: string;
};

export function getGenerationErrorInfo(error: unknown): GenerationErrorInfo {
  const requestId = error instanceof ApiRequestError ? error.requestId : undefined;
  const result = (type: GenerationErrorType, message: string): GenerationErrorInfo => ({ type, message, requestId });
  if (error instanceof ApiRequestError) {
    if (error.code === "timeout" || error.code === "MODEL_TIMEOUT") {
      return result("timeout", "生成时间超过预期，请稍后重试。您的输入内容仍然保留。");
    }
    if (error.code === "INPUT_TOO_LARGE") return result("input", error.message);
    if (error.code === "USER_RATE_LIMITED" || error.code === "IP_RATE_LIMITED") {
      return result("rate_limit", error.message || "操作有些频繁，请稍后再试。");
    }
    if (["GENERATION_QUEUE_FULL", "GENERATION_ALREADY_RUNNING", "PROTECTION_DEGRADED"].includes(error.code || "")) {
      return result("capacity", error.message || "当前生成任务较多，请稍后再试。");
    }
    if (error.code === "GENERATION_EXPIRED") {
      return result("timeout", "生成任务等待时间过长，请重新提交。您的输入内容仍然保留。");
    }
    if (error.code === "DAILY_BUDGET_REACHED") {
      return result("budget", "今日生成容量已达到上限，请稍后再试。您的输入内容仍然保留。");
    }
    if (error.status === 401 || error.status === 403) {
      return result("configuration", "生成服务配置异常，请联系网站维护者。");
    }
    if (error.status && error.status >= 500) {
      return result("server", "生成服务暂时出现问题，请稍后重新尝试。");
    }
    if (error.code === "network") {
      return result("network", "暂时无法连接生成服务，请检查网络后重试。您的输入内容不会丢失。");
    }
  }

  const rawMessage = error instanceof Error ? error.message : String(error);
  if (/json|parse|schema|validation|字段|结构|不完整/i.test(rawMessage)) {
    return result("invalid_response", "本次生成结果不完整，请重新生成一次。");
  }
  if (/timeout|timed out|超时|abort/i.test(rawMessage)) {
    return result("timeout", "生成时间超过预期，请稍后重试。您的输入内容仍然保留。");
  }
  if (/failed to fetch|network|网络|连接/i.test(rawMessage)) {
    return result("network", "暂时无法连接生成服务，请检查网络后重试。您的输入内容不会丢失。");
  }
  return result("unknown", "本次生成没有成功，请稍后重试。您的输入内容仍然保留。");
}

export function getOperationErrorMessage(error: unknown, operation: "docx" | "feedback" | "deletion") {
  const info = getGenerationErrorInfo(error);
  if (operation === "docx") {
    if (info.type === "network") return "暂时无法连接文件服务，请检查网络后重试。当前简历结果仍然保留。";
    if (info.type === "configuration") return "文件服务配置异常，请联系网站维护者。";
    return "暂时无法生成或下载 DOCX，请稍后重试。当前简历结果仍然保留。";
  }
  if (operation === "deletion") {
    if (info.type === "network") return "暂时无法连接数据服务，请检查网络后重试。现有内容不会被清空。";
    return "数据删除失败，请稍后重试。现有内容不会被前端静默清空。";
  }
  if (info.type === "network") return "暂时无法提交评价，请检查网络后重试。您填写的内容仍然保留。";
  return "评价暂时没有提交成功，请稍后重试。您填写的内容仍然保留。";
}
