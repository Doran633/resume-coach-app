import { Button, Card, Col, Input, Progress, Row, Space, Typography, message } from "antd";
import { useState } from "react";
import { generateExperience, trackEvent } from "../api/client";
import { useAppStore } from "../store/appStore";
import type { ClaimResult } from "../types/api";

const riskMeta = {
  green: { label: "可直接使用", className: "risk-green" },
  yellow: { label: "建议准备", className: "risk-yellow" },
  red: { label: "建议降级", className: "risk-red" },
  black: { label: "不要硬写", className: "risk-black" }
} as const;

function compactText(text: string, fallback = "暂未生成") {
  return text?.trim() || fallback;
}

function strengthenLevel(score: number) {
  if (score >= 80) return "高";
  if (score >= 60) return "中";
  return "待补充";
}

function VersionCard({ title, tone, text }: { title: string; tone: string; text: string }) {
  return (
    <div className="version-card">
      <div className="version-head">
        <span>{title}</span>
        <small>{tone}</small>
      </div>
      <p>{compactText(text)}</p>
    </div>
  );
}

function ProjectPreview({ project }: { project: Record<string, any> }) {
  const details = Array.isArray(project.details) ? project.details.slice(0, 3) : [];
  return (
    <Card className="panel project-preview">
      <div className="section-title">
        <div>
          <Typography.Title level={4}>项目经历预览</Typography.Title>
          <p>先预览一段可放进正式简历的项目写法，方便你判断重点是否准确。</p>
        </div>
      </div>
      <div className="project-title-line">
        <div>
          <small>项目名称</small>
          <strong>{compactText(project.name, "项目名称待补充")}</strong>
        </div>
        <div>
          <small>项目类型</small>
          <span>{compactText(project.meta, "项目类型待补充")}</span>
        </div>
        <div>
          <small>项目时间</small>
          <span>{compactText(project.time, "项目时间待补充")}</span>
        </div>
      </div>
      <div className="project-fields">
        <div>
          <span>项目简介</span>
          <p>{compactText(project.intro)}</p>
        </div>
        <div>
          <span>我的职责</span>
          <p>{compactText(project.role)}</p>
        </div>
        {details.length > 0 && (
          <div>
            <span>技术细节</span>
            <ul>
              {details.map((item: string) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}

function ClaimRow({ claim }: { claim: ClaimResult }) {
  const meta = riskMeta[claim.risk_level];
  const prepare = claim.knowledge_to_prepare.slice(0, 2).join(" / ");
  return (
    <div className="claim-row">
      <div>
        <strong>{claim.claim}</strong>
        <span>{claim.risk_reason || claim.evidence || meta.label}</span>
        {prepare && <em>准备：{prepare}</em>}
      </div>
      <span className={`risk-dot ${meta.className}`} title={meta.label} />
    </div>
  );
}

export default function ResultPage() {
  const { generation, identity, lastRequest, setGeneration, setLastRequest, setStep } = useAppStore();
  const [followup, setFollowup] = useState("");
  const [regenerating, setRegenerating] = useState(false);

  if (!generation) return null;
  const result = generation.result;

  const copy = async () => {
    await navigator.clipboard.writeText(result.recommended_version);
    await trackEvent(identity, "copy_result", { generation_result_id: generation.generation_result_id });
    message.success("已复制推荐版本");
  };

  const regenerateWithFollowup = async () => {
    if (!lastRequest) {
      message.warning("请先返回输入页补充信息");
      return;
    }
    if (followup.trim().length < 4) {
      message.warning("请至少补充一句关键信息");
      return;
    }

    const nextRequest = {
      ...lastRequest,
      raw_input: `${lastRequest.raw_input}\n\n补充信息：${followup.trim()}`
    };

    setRegenerating(true);
    setLastRequest(nextRequest);
    try {
      const next = await generateExperience(identity, nextRequest);
      setGeneration(next);
      setFollowup("");
      message.success("已根据补充信息重新生成");
    } catch (error) {
      message.error(`重新生成失败：${String(error).slice(0, 80)}`);
    } finally {
      setRegenerating(false);
    }
  };

  const confirmedFacts = result.confirmed_facts.slice(0, 4);
  const missingQuestions = result.missing_questions.slice(0, 3);
  const firstProject = result.resume_sections.projects?.[0];

  return (
    <Space direction="vertical" size="large" className="wide result-view">
      <Card className="panel coach-summary">
        <div className="summary-main">
          <div className="summary-copy">
            <span className="summary-eyebrow">求职教练建议</span>
            <Typography.Title level={3}>先把经历写强，再告诉你怎么接住</Typography.Title>
            <p>基于你的真实经历生成不同强度的简历表达，并同步标出每个强表达背后需要准备的证据、技术点和面试回答。</p>
          </div>
          <div className="metric-card">
            <Progress type="circle" percent={result.completeness_score} size={78} />
            <div>
              <strong>信息完整度</strong>
              <span>{strengthenLevel(result.completeness_score)}强化空间</span>
            </div>
          </div>
        </div>
        <div className="fact-strip">
          {confirmedFacts.map((item) => <span key={item}>{item}</span>)}
        </div>
      </Card>

      <Card className="panel recommended-panel">
        <div className="section-title">
          <div>
            <Typography.Title level={4}>最终推荐版本</Typography.Title>
            <p>建议优先使用这一版，再根据面试准备情况微调。</p>
          </div>
          <Button onClick={copy}>复制</Button>
        </div>
        <div className="recommended-text">{compactText(result.recommended_version)}</div>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <VersionCard title="普通包装版" tone="稳妥可用" text={result.normal_version} />
        </Col>
        <Col xs={24} md={8}>
          <VersionCard title="大胆包装版" tone="更强岗位感" text={result.bold_version} />
        </Col>
        <Col xs={24} md={8}>
          <VersionCard title="边界参考版" tone="知道哪里别越界" text={result.boundary_version} />
        </Col>
      </Row>

      {firstProject && <ProjectPreview project={firstProject} />}

      <Card className="panel claim-panel" onMouseEnter={() => trackEvent(identity, "view_claim_risk", { generation_result_id: generation.generation_result_id })}>
        <div className="section-title">
          <div>
            <Typography.Title level={4}>强表达承接检查</Typography.Title>
            <p>绿色放心写，黄色补充准备，红色建议换说法。目标是让你的简历更强，也更稳。</p>
          </div>
          <div className="risk-legend">
            <span><i className="risk-dot risk-green" />可用</span>
            <span><i className="risk-dot risk-yellow" />准备</span>
            <span><i className="risk-dot risk-red" />降级</span>
          </div>
        </div>
        <div className="claim-list">
          {result.claims.map((claim) => <ClaimRow key={`${claim.claim}-${claim.risk_level}`} claim={claim} />)}
        </div>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card className="panel compact-panel" title="下一步追问">
            {missingQuestions.map((item) => <p key={item}>{item}</p>)}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card className="panel compact-panel" title="面试承接准备">
            {result.interview_plan.slice(0, 4).map((item) => <p key={item}>{item}</p>)}
          </Card>
        </Col>
      </Row>

      <Card className="panel followup-panel">
        <div className="section-title">
          <div>
            <Typography.Title level={4}>补充信息，继续强化</Typography.Title>
            <p>如果某个点不够准，可以直接补充证据、技术细节或项目边界，我会重新生成一版。</p>
          </div>
        </div>
        <Input.TextArea
          rows={4}
          value={followup}
          onChange={(event) => setFollowup(event.target.value)}
          placeholder="例如：500人是累计真实用户，不是同时在线；RAG 已实现 chunk、embedding、top-k 检索，但 rerank 还在规划。"
        />
        <Space className="footer-actions">
          <Button onClick={() => setStep(0)}>返回修改原始输入</Button>
          <Button type="primary" loading={regenerating} onClick={regenerateWithFollowup}>
            {regenerating ? "正在重新生成" : "补充后重新生成"}
          </Button>
          <Button size="large" onClick={() => setStep(2)}>
            进入导出与反馈
          </Button>
        </Space>
      </Card>
    </Space>
  );
}
