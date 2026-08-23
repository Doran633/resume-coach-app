import { Button, Card, Col, Collapse, Input, Progress, Row, Space, Tabs, Tag, Typography, message } from "antd";
import { useState } from "react";
import { generateExperience, trackEvent } from "../api/client";
import { useAppStore } from "../store/appStore";
import type { ClaimResult } from "../types/api";

const riskMeta = {
  green: { label: "可用", longLabel: "可直接使用", className: "risk-green", color: "success" },
  yellow: { label: "准备", longLabel: "建议准备", className: "risk-yellow", color: "warning" },
  red: { label: "降级", longLabel: "建议降级", className: "risk-red", color: "error" },
  black: { label: "不要硬写", longLabel: "不要硬写", className: "risk-black", color: "default" }
} as const;

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

function compactText(text: string, fallback = "暂未生成") {
  return text?.trim() || fallback;
}

function cleanDisplayText(text: string, fallback = "暂未生成") {
  const cleaned = displayReplacements.reduce((current, [pattern, replacement]) => current.replace(pattern, replacement), compactText(text, fallback));
  return cleaned.replace(/\s+/g, " ").trim();
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
      <p>{cleanDisplayText(text)}</p>
    </div>
  );
}

function ProjectPreview({ project }: { project: Record<string, any> }) {
  const details = Array.isArray(project.details) ? project.details.slice(0, 3) : [];
  return (
    <div className="project-preview">
      <div className="section-title">
        <div>
          <Typography.Title level={4}>项目经历预览</Typography.Title>
          <p>先预览一段可放进正式简历的项目写法，方便你判断重点是否准确。</p>
        </div>
      </div>
      <div className="project-title-line">
        <div>
          <small>项目名称</small>
          <strong>{cleanDisplayText(project.name, "项目名称待补充")}</strong>
        </div>
        <div>
          <small>项目类型</small>
          <span>{cleanDisplayText(project.meta, "项目类型待补充")}</span>
        </div>
        <div>
          <small>项目时间</small>
          <span>{cleanDisplayText(project.time, "项目时间待补充")}</span>
        </div>
      </div>
      <div className="project-fields">
        <div>
          <span>项目简介</span>
          <p>{cleanDisplayText(project.intro)}</p>
        </div>
        <div>
          <span>我的职责</span>
          <p>{cleanDisplayText(project.role)}</p>
        </div>
        {details.length > 0 && (
          <div>
            <span>技术细节</span>
            <ul>
              {details.map((item: string) => <li key={item}>{cleanDisplayText(item)}</li>)}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function FactStrip({ facts }: { facts: string[] }) {
  if (!facts.length) return <p className="empty-hint">暂未识别到足够明确的事实，可以在补充信息里继续完善。</p>;
  return (
    <div className="fact-strip">
      {facts.map((item) => <span key={item}>{cleanDisplayText(item)}</span>)}
    </div>
  );
}

function ClaimSummary({ claim }: { claim: ClaimResult }) {
  const meta = riskMeta[claim.risk_level];
  const suggestion = claim.risk_reason || claim.evidence || meta.longLabel;
  return (
    <div className="claim-summary">
      <div>
        <strong>{cleanDisplayText(claim.claim)}</strong>
        <span>{cleanDisplayText(suggestion)}</span>
      </div>
      <Tag color={meta.color}>{meta.label}</Tag>
    </div>
  );
}

function DetailBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="claim-detail-block">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

function ClaimCheck({ claims, onExpand }: { claims: ClaimResult[]; onExpand: (claim: ClaimResult) => void }) {
  if (!claims.length) {
    return <p className="empty-hint">暂未生成承接检查。你可以补充更多项目证据后重新生成。</p>;
  }

  return (
    <div className="claim-workbench">
      <div className="risk-legend">
        <span><i className="risk-dot risk-green" />可用</span>
        <span><i className="risk-dot risk-yellow" />准备</span>
        <span><i className="risk-dot risk-red" />降级</span>
        <span><i className="risk-dot risk-black" />不要硬写</span>
      </div>
      <Collapse
        className="claim-collapse"
        ghost
        onChange={(keys) => {
          const activeKeys = Array.isArray(keys) ? keys : [keys].filter(Boolean);
          const firstKey = String(activeKeys[0] ?? "");
          const index = Number(firstKey.replace("claim-", ""));
          if (activeKeys.length && claims[index]) onExpand(claims[index]);
        }}
        items={claims.map((claim, index) => ({
          key: `claim-${index}`,
          label: <ClaimSummary claim={claim} />,
          children: (
            <div className="claim-detail-grid">
              <DetailBlock title="支撑证据">
                <p>{cleanDisplayText(claim.evidence, "需要补充可验证证据。")}</p>
              </DetailBlock>
              <DetailBlock title="风险原因">
                <p>{cleanDisplayText(claim.risk_reason, "暂无明显风险说明。")}</p>
              </DetailBlock>
              <DetailBlock title="面试追问">
                <ul>
                  {claim.interview_questions.length ? claim.interview_questions.map((item) => <li key={item}>{cleanDisplayText(item)}</li>) : <li>暂无追问，建议准备项目背景和个人贡献。</li>}
                </ul>
              </DetailBlock>
              <DetailBlock title="知识补齐">
                <ul>
                  {claim.knowledge_to_prepare.length ? claim.knowledge_to_prepare.map((item) => <li key={item}>{cleanDisplayText(item)}</li>) : <li>暂无专项知识点。</li>}
                </ul>
              </DetailBlock>
              <DetailBlock title="降级表达">
                <p>{cleanDisplayText(claim.downgrade_wording, "准备不足时建议降低职责强度。")}</p>
              </DetailBlock>
            </div>
          )
        }))}
      />
    </div>
  );
}

function InterviewCards({ items }: { items: string[] }) {
  if (!items.length) return <p className="empty-hint">暂未生成面试承接准备。</p>;
  return (
    <div className="interview-card-list">
      {items.slice(0, 6).map((item, index) => (
        <div className="interview-card" key={`${item}-${index}`}>
          <small>问题 {index + 1}</small>
          <p>{cleanDisplayText(item)}</p>
        </div>
      ))}
    </div>
  );
}

function KnowledgeList({ items }: { items: string[] }) {
  if (!items.length) return <p className="empty-hint">暂未生成知识补齐清单。</p>;
  return (
    <div className="knowledge-list">
      {items.slice(0, 8).map((item) => <span key={item}>{cleanDisplayText(item)}</span>)}
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

    await trackEvent(identity, "submit_followup", {
      generation_result_id: generation.generation_result_id,
      followup_length: followup.trim().length
    });
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

  const confirmedFacts = result.confirmed_facts.slice(0, 5);
  const missingQuestions = result.missing_questions.slice(0, 5);
  const firstProject = result.resume_sections.projects?.[0];
  const education = result.resume_sections.education ?? {};
  const summary = result.resume_sections.summary.slice(0, 3);
  const skills = result.resume_sections.skills.slice(0, 8);

  const tabItems = [
    {
      key: "overview",
      label: "定位总览",
      children: (
        <Space direction="vertical" size="large" className="wide">
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
            <FactStrip facts={confirmedFacts} />
          </Card>

          <Card className="panel recommended-panel">
            <div className="section-title">
              <div>
                <Typography.Title level={4}>最终推荐版本</Typography.Title>
                <p>建议优先使用这一版，再根据面试准备情况微调。</p>
              </div>
              <Button onClick={copy}>复制</Button>
            </div>
            <div className="recommended-text">{cleanDisplayText(result.recommended_version)}</div>
          </Card>
        </Space>
      )
    },
    {
      key: "versions",
      label: "三档包装",
      children: (
        <Row gutter={[16, 16]} className="version-grid">
          <Col xs={24} md={8}>
            <VersionCard title="基础增强版" tone="写完整、写专业" text={result.normal_version} />
          </Col>
          <Col xs={24} md={8}>
            <VersionCard title="重点放大版" tone="推荐使用" text={result.bold_version} />
          </Col>
          <Col xs={24} md={8}>
            <VersionCard title="边界测试版" tone="知道哪里别越界" text={result.boundary_version} />
          </Col>
        </Row>
      )
    },
    {
      key: "claims",
      label: "承接检查",
      children: (
        <Card className="panel claim-panel" onMouseEnter={() => trackEvent(identity, "view_claim_risk", { generation_result_id: generation.generation_result_id })}>
          <div className="section-title">
            <div>
              <Typography.Title level={4}>强表达承接检查</Typography.Title>
              <p>这里不是挑刺，而是帮你判断哪些表达可以放心写，哪些需要提前准备证据和回答。</p>
            </div>
          </div>
          <ClaimCheck
            claims={result.claims}
            onExpand={(claim) => trackEvent(identity, "expand_claim", {
              generation_result_id: generation.generation_result_id,
              claim: claim.claim,
              risk_level: claim.risk_level
            })}
          />
        </Card>
      )
    },
    {
      key: "interview",
      label: "面试准备",
      children: (
        <Row gutter={[16, 16]} align="stretch">
          <Col xs={24} lg={14}>
            <Card className="panel interview-panel" title="面试承接准备">
              <InterviewCards items={result.interview_plan} />
            </Card>
          </Col>
          <Col xs={24} lg={10}>
            <Card className="panel interview-panel" title="知识补齐清单">
              <KnowledgeList items={result.knowledge_checklist} />
            </Card>
          </Col>
        </Row>
      )
    },
    {
      key: "resume",
      label: "简历预览",
      children: (
        <Card className="panel resume-preview-panel">
          {summary.length > 0 && (
            <div className="resume-preview-block">
              <Typography.Title level={4}>个人优势</Typography.Title>
              <ul>{summary.map((item) => <li key={item}>{cleanDisplayText(item)}</li>)}</ul>
            </div>
          )}
          {Object.keys(education).length > 0 && (
            <div className="resume-preview-block">
              <Typography.Title level={4}>教育经历</Typography.Title>
              <p>{Object.entries(education).map(([key, value]) => `${cleanDisplayText(key)}：${cleanDisplayText(String(value))}`).join(" / ")}</p>
            </div>
          )}
          {skills.length > 0 && (
            <div className="resume-preview-block">
              <Typography.Title level={4}>技能栈</Typography.Title>
              <div className="knowledge-list">{skills.map((item) => <span key={item}>{cleanDisplayText(item)}</span>)}</div>
            </div>
          )}
          {firstProject ? <ProjectPreview project={firstProject} /> : <p className="empty-hint">暂未生成项目经历预览。</p>}
        </Card>
      )
    }
  ];

  return (
    <Space direction="vertical" size="large" className="wide result-view">
      <Card className="panel result-tabs-card">
        <Tabs
          items={tabItems}
          onChange={(key) => trackEvent(identity, "view_result_tab", { generation_result_id: generation.generation_result_id, tab_key: key })}
        />
      </Card>

      <Row gutter={[16, 16]} align="stretch" className="followup-grid">
        <Col xs={24} lg={12}>
          <Card className="panel compact-panel equal-panel" title="还需要补充什么">
            {missingQuestions.length ? missingQuestions.map((item) => <p key={item}>{cleanDisplayText(item)}</p>) : <p className="empty-hint">当前信息已经比较完整，也可以补充数据证据、技术细节或项目边界继续强化。</p>}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card className="panel followup-panel equal-panel">
            <div className="section-title">
              <div>
                <Typography.Title level={4}>补充信息，继续强化</Typography.Title>
                <p>把真实证据、技术细节或边界条件补进来，我会重新生成一版。</p>
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
        </Col>
      </Row>
    </Space>
  );
}
