import type { GenerationResult } from "../types/api";

export type InterviewGroupKey = "questions" | "knowledge" | "evidence" | "boundary";
export interface InterviewPreparationItem { text: string; note?: string }
export type InterviewPreparationGroups = Record<InterviewGroupKey, InterviewPreparationItem[]>;

const replacements: Array<[RegExp, string]> = [
  [/\bquestion\s*[:：]/gi, "面试问题："],
  [/\banswer_points\s*[:：]/gi, "回答要点："],
  [/\bknowledge_to_prepare\s*[:：]/gi, "准备重点："],
  [/\bdowngrade_wording\s*[:：]/gi, "降级表达："]
];

export function cleanInterviewText(value: string) {
  return replacements.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), value || "").replace(/\s+/g, " ").trim();
}

function fingerprint(value: string) {
  return cleanInterviewText(value).toLowerCase().replace(/[\s，。！？、；：,.!?;:()（）\[\]【】"']/g, "");
}

function pushUnique(items: InterviewPreparationItem[], candidate: InterviewPreparationItem) {
  const text = cleanInterviewText(candidate.text);
  if (!text) return;
  const key = fingerprint(text);
  const duplicate = items.some((item) => {
    const existing = fingerprint(item.text);
    return existing === key || (Math.min(existing.length, key.length) >= 14 && (existing.includes(key) || key.includes(existing)));
  });
  if (!duplicate) items.push({ text, note: candidate.note ? cleanInterviewText(candidate.note) : undefined });
}

function classifyGeneral(text: string): InterviewGroupKey {
  if (/降级|边界|不足|未实现|规划|口径|谨慎|不建议/.test(text)) return "boundary";
  if (/证据|日志|仓库|截图|数据|指标|部署记录|测试报告|用户反馈|证书|PPT|Commit|PR/i.test(text)) return "evidence";
  if (/RAG|Agent|React|Vue|FastAPI|SQL|模型|向量|API|TypeScript|LangChain|LangGraph|Chunk|Top-K|检索|数据库/i.test(text)) return "knowledge";
  return "questions";
}

export function buildInterviewPreparation(result?: GenerationResult): InterviewPreparationGroups {
  const groups: InterviewPreparationGroups = { questions: [], knowledge: [], evidence: [], boundary: [] };
  if (!result) return groups;
  result.interview_plan.forEach((text) => pushUnique(groups.questions, { text }));
  result.knowledge_checklist.forEach((text) => pushUnique(groups.knowledge, { text }));
  result.missing_questions.forEach((text) => pushUnique(groups.questions, { text, note: "建议补充事实口径后再完善回答。" }));
  result.resume_sections.interview_preparation.forEach((text) => pushUnique(groups[classifyGeneral(text)], { text }));
  result.claims.forEach((claim) => {
    claim.interview_questions.forEach((text) => pushUnique(groups.questions, { text, note: claim.risk_reason || `关联表达：${claim.claim}` }));
    claim.knowledge_to_prepare.forEach((text) => pushUnique(groups.knowledge, { text, note: `关联表达：${claim.claim}` }));
    if (claim.evidence) pushUnique(groups.evidence, { text: claim.evidence, note: `用于支撑：${claim.claim}` });
    if (claim.downgrade_wording) pushUnique(groups.boundary, { text: claim.downgrade_wording, note: `当前强化表达：${claim.claim}` });
  });
  return groups;
}

export function formatInterviewItems(title: string, items: InterviewPreparationItem[]) {
  return `${title}\n${items.map((item, index) => `${index + 1}. ${item.text}${item.note ? `\n   ${item.note}` : ""}`).join("\n")}`;
}
