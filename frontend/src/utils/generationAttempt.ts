export function createAttemptId() {
  const suffix = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  return `attempt_${suffix}`;
}

export function estimateExperienceCount(rawInput: string) {
  const text = rawInput.trim();
  if (!text) return 0;
  const explicitHeaders = text.match(/(?:^|\n)\s*(?:#{1,4}\s*)?(?:项目|经历)[一二三四五六七八九十\d]+|(?:^|\n)\s*(?:实习|科研|研究|竞赛|比赛|开源|校园|社团)经历\s*[：:｜|]/g);
  if (explicitHeaders?.length) return Math.min(explicitHeaders.length, 10);
  const paragraphs = text.split(/\n\s*\n+/).map((item) => item.trim()).filter((item) => item.length >= 20);
  return Math.max(1, Math.min(paragraphs.length, 10));
}

export function hasTechnicalTerms(rawInput: string) {
  return /React|Vue|TypeScript|JavaScript|Python|Java|FastAPI|Spring|Node|SQL|SQLite|MySQL|Redis|Docker|Nginx|RAG|Agent|LangChain|LangGraph|Embedding|API|接口|数据库|模型|检索/i.test(rawInput);
}
