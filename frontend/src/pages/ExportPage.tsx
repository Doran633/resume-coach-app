import { Button, Card, Col, Form, Input, Radio, Row, Space, Typography, message } from "antd";
import { useEffect, useMemo } from "react";
import { buildApiUrl, createDocx, submitFeedback, trackEvent } from "../api/client";
import { useAppStore } from "../store/appStore";
import type { GenerationResult } from "../types/api";

const displayReplacements: Array<[RegExp, string]> = [
  [/\bquestion\s*[:：]/gi, "面试问题："],
  [/\banswer_points\s*[:：]/gi, "回答要点："],
  [/\brole\s*[:：]/gi, "我的职责："],
  [/\bdetails\s*[:：]/gi, "技术细节："],
  [/\bintro\s*[:：]/gi, "项目简介："],
  [/\bmeta\s*[:：]/gi, "项目类型："],
  [/\bname\s*[:：]/gi, "项目名称："],
  [/\btime\s*[:：]/gi, "项目时间："]
];

const planGroups = [
  { key: "tech", title: "技术知识补齐" },
  { key: "interview", title: "面试追问准备" },
  { key: "evidence", title: "证据材料准备" },
  { key: "downgrade", title: "降级表达准备" }
] as const;

type PlanGroupKey = (typeof planGroups)[number]["key"];

function cleanDisplayText(text: string) {
  const cleaned = displayReplacements.reduce((current, [pattern, replacement]) => current.replace(pattern, replacement), text || "");
  return cleaned.replace(/\s+/g, " ").trim();
}

function uniqueItems(items: string[]) {
  const seen = new Set<string>();
  return items
    .map(cleanDisplayText)
    .filter(Boolean)
    .filter((item) => {
      if (seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function classifyPlanItem(item: string): PlanGroupKey {
  if (/降级|边界|不足|未实现|规划/.test(item)) return "downgrade";
  if (/证据|日志|仓库|截图|数据|指标|口径/.test(item)) return "evidence";
  if (/RAG|Agent|React|FastAPI|SQL|模型|向量|API|TypeScript|LangChain|LangGraph|数据库|检索/i.test(item)) return "tech";
  if (/面试|问|介绍|解释|回答/.test(item)) return "interview";
  return "interview";
}

function buildInterviewPlanGroups(result: GenerationResult | undefined) {
  if (!result) {
    return {
      tech: [],
      interview: [],
      evidence: [],
      downgrade: []
    };
  }

  const orderedItems = uniqueItems([
    ...result.resume_sections.interview_preparation,
    ...result.knowledge_checklist,
    ...result.interview_plan
  ]);
  const groups: Record<PlanGroupKey, string[]> = {
    tech: [],
    interview: [],
    evidence: [],
    downgrade: []
  };

  orderedItems.forEach((item) => {
    groups[classifyPlanItem(item)].push(item);
  });

  return groups;
}

export default function ExportPage() {
  const { generation, identity, setStep } = useAppStore();

  const planGroupsByType = useMemo(() => buildInterviewPlanGroups(generation?.result), [generation?.result]);
  const hasInterviewPlan = Object.values(planGroupsByType).some((items) => items.length > 0);

  useEffect(() => {
    if (!generation || !hasInterviewPlan) return;
    void trackEvent(identity, "view_export_interview_plan", {
      generation_result_id: generation.generation_result_id
    });
  }, [generation, hasInterviewPlan, identity]);

  if (!generation) return null;

  const generateDocx = async () => {
    try {
      const file = await createDocx(identity, generation.generation_result_id);
      await trackEvent(identity, "generate_docx", { file_id: file.file_id });
      window.open(buildApiUrl(file.download_url), "_blank");
      await trackEvent(identity, "download_docx", { file_id: file.file_id });
      message.success("DOCX 已生成");
    } catch (error) {
      message.error("DOCX 生成失败");
    }
  };

  const onFinish = async (values: any) => {
    await submitFeedback(identity, {
      generation_result_id: generation.generation_result_id,
      ...values
    });
    await trackEvent(identity, "submit_feedback", values);
    message.success("感谢反馈，v0.1 数据已记录");
  };

  return (
    <Space direction="vertical" size="large" className="wide export-page">
      <Card className="panel export-hero" title="导出正式简历">
        <Typography.Paragraph>
          当前版本会根据推荐表达生成基础技术简历 DOCX，文件保存在后端 outputs 目录。
        </Typography.Paragraph>
        <Space wrap>
          <Button onClick={() => setStep(1)}>返回结果</Button>
          <Button type="primary" onClick={generateDocx}>生成并下载 DOCX</Button>
        </Space>
      </Card>

      <Card className="panel interview-delivery" title="面试准备清单">
        <Typography.Paragraph>
          下载简历后，可以按这份清单补齐技术、证据和回答口径。
        </Typography.Paragraph>
        {hasInterviewPlan ? (
          <Row gutter={[16, 16]}>
            {planGroups.map((group) => (
              <Col xs={24} md={12} key={group.key}>
                <div className="delivery-card">
                  <strong>{group.title}</strong>
                  {planGroupsByType[group.key].length ? (
                    <ul>
                      {planGroupsByType[group.key].slice(0, 5).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  ) : (
                    <p>暂无专项内容，可以根据最终简历表达自行补充。</p>
                  )}
                </div>
              </Col>
            ))}
          </Row>
        ) : (
          <p className="empty-hint">暂未生成面试准备清单，可以返回结果页补充更多经历细节后重新生成。</p>
        )}
      </Card>

      <Card className="panel" title="结果反馈">
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item label="你认为这个服务相比当前市场大模型效果如何？" name="model_comparison" rules={[{ required: true }]}>
            <Radio.Group options={["明显更好", "略好一些", "差不多", "不如直接用大模型"].map((value) => ({ label: value, value }))} />
          </Form.Item>
          <Form.Item label="你认为这样的服务价值多少？" name="value_choice" rules={[{ required: true }]}>
            <Radio.Group options={["0元", "2.99元", "9.99元"].map((value) => ({ label: value, value }))} />
          </Form.Item>
          <Form.Item label="可选补充反馈" name="comment">
            <Input.TextArea rows={4} placeholder="哪里最有用？哪里最需要改？" />
          </Form.Item>
          <Button type="primary" htmlType="submit">提交反馈</Button>
        </Form>
      </Card>
    </Space>
  );
}
