import { Alert, Button, Card, Form, Input, Radio, Select, Space, Typography, message } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { generateExperience, trackEvent } from "../api/client";
import { useAppStore } from "../store/appStore";

const packagingLevelMap: Record<string, string> = {
  基础增强: "稳妥",
  重点放大: "大胆",
  边界测试: "极限"
};

const packagingLevelDisplayMap: Record<string, string> = {
  稳妥: "基础增强",
  大胆: "重点放大",
  极限: "边界测试"
};

const draftKeys = {
  raw_input: "resume_coach_draft_input",
  target_role: "resume_coach_draft_target_role",
  packaging_level: "resume_coach_draft_packaging_level",
  experience_type: "resume_coach_draft_experience_type"
};

const packagingLevels = [
  { label: "基础增强", value: "基础增强", description: "适合想把经历写完整、写专业，表达会比普通润色更强。" },
  { label: "重点放大", value: "重点放大", description: "推荐使用，围绕目标岗位强化职责、技术深度和结果表达，同时给出面试承接准备。" },
  { label: "边界测试", value: "边界测试", description: "用于查看表达边界和露馅风险，不建议直接照抄投递。" }
];

const targetRoles = ["AI / 大模型 / Agent", "前端开发", "后端开发", "测试开发", "数据分析", "产品 / 运营", "泛互联网岗位"];

const exampleTemplates = [
  {
    type: "项目经历",
    text: "我做过一个 [项目名称]，目标是解决 [具体问题]。我主要负责 [模块/功能]，使用了 [技术栈]。项目实现了 [功能点]，有 [用户数/访问量/部署记录/代码仓库] 作为证明。我想投 [目标岗位]，希望这段经历能包装得更有岗位匹配度，但不要写成完全无法解释的内容。"
  },
  {
    type: "实习经历",
    text: "我在 [公司/团队] 做过 [岗位/方向] 实习，主要参与 [业务/系统/流程]。我负责 [具体工作]，使用 [工具/技术] 完成了 [交付内容]。这段经历有 [数据、上线记录、导师评价、产出文档] 可以支撑，希望突出我的岗位匹配度和实际贡献。"
  },
  {
    type: "开源经历",
    text: "我参与过 [开源项目/社区]，主要贡献是 [修复问题、补充文档、提交 PR、维护功能]。我理解了项目的 [核心模块/工作流/工程规范]，贡献可以通过 [PR 链接、issue、star、commit 记录] 证明。我希望把它包装成有价值的开源协作经历。"
  },
  {
    type: "比赛经历",
    text: "我参加过 [比赛名称]，项目方向是 [赛题/业务问题]。我负责 [建模、开发、数据处理、展示、答辩]，使用了 [技术/工具]，最终获得 [名次/奖项/入围/成绩]。希望突出解决问题能力、技术落地能力和团队贡献。"
  },
  {
    type: "大模型 / Agent 经历",
    text: "我做过一个 [大模型/Agent 应用]，目标是 [自动化流程/知识问答/内容生成/任务执行]。我主要负责 [RAG、工具调用、工作流编排、提示词工程、评测]，使用了 [模型/API/框架/数据库]。目前实现了 [具体功能]，还有 [未完成或规划中的能力]，希望包装得更适合 AI / 大模型 / Agent 岗位。"
  }
];

const writingFormat = [
  "我做过一个【项目 / 实习 / 开源 / 比赛经历】，目标是解决【具体问题】。",
  "我主要负责【模块 / 功能 / 流程】，使用了【技术栈 / 工具 / 平台】完成【具体工作】。",
  "目前有【用户数 / 访问量 / 日志 / 仓库 / 文档 / 反馈】作为证据，希望重点放大【目标岗位相关能力】。"
];

type QualityHint = {
  type: string;
  text: string;
};

function getQualityHints(rawInput = ""): QualityHint[] {
  const value = rawInput.trim();
  if (!value) return [];

  const hints: QualityHint[] = [];
  const technicalPattern = /React|Vue|TypeScript|JavaScript|FastAPI|Python|Java|Spring|Node|RAG|Agent|LangChain|LangGraph|SQL|SQLite|MySQL|Redis|Docker|API|接口|前端|后端|数据库|大模型|向量|模型|检索/i;
  const resultPattern = /上线|部署|日志|反馈|用户|访问|star|stars|排名|获奖|性能|指标|并发|仓库|GitHub|PR|数据|证明|成果|完成|实现|支持|提升|优化/i;

  if (value.length < 80) {
    hints.push({ type: "too_short", text: "建议补充技术栈、负责模块和结果证据。" });
  }
  if (!/\d/.test(value)) {
    hints.push({ type: "no_numbers", text: "如果有用户数、访问量、star、性能指标、比赛名次，可以补充。" });
  }
  if (!technicalPattern.test(value)) {
    hints.push({ type: "no_tech", text: "建议补充技术栈、工具或平台。" });
  }
  if (!resultPattern.test(value)) {
    hints.push({ type: "no_evidence", text: "建议补充上线、部署、日志、反馈、排名、仓库等证明材料。" });
  }
  return hints;
}

export default function InputPage() {
  const [form] = Form.useForm();
  const [generating, setGenerating] = useState(false);
  const { identity, lastRequest, setGeneration, setLastRequest } = useAppStore();
  const rawInput = Form.useWatch("raw_input", form) ?? "";
  const packagingLevel = Form.useWatch("packaging_level", form) ?? "重点放大";
  const trackedHintKeyRef = useRef("");
  const qualityHints = useMemo(() => getQualityHints(rawInput), [rawInput]);
  const initialValues = useMemo(() => {
    const savedPackagingLevel = localStorage.getItem(draftKeys.packaging_level) || "重点放大";
    return {
      target_role: lastRequest?.target_role || localStorage.getItem(draftKeys.target_role) || "AI / 大模型 / Agent",
      mode: lastRequest?.mode || "single_experience",
      packaging_level: lastRequest?.packaging_level
        ? packagingLevelDisplayMap[lastRequest.packaging_level] ?? lastRequest.packaging_level
        : packagingLevelDisplayMap[savedPackagingLevel] ?? savedPackagingLevel,
      experience_type: lastRequest?.experience_type || localStorage.getItem(draftKeys.experience_type) || "项目",
      raw_input: lastRequest?.raw_input || localStorage.getItem(draftKeys.raw_input) || ""
    };
  }, [lastRequest]);

  useEffect(() => {
    if (!qualityHints.length) return;
    const hintTypes = qualityHints.map((item) => item.type);
    const nextKey = hintTypes.join("|");
    if (nextKey === trackedHintKeyRef.current) return;
    trackedHintKeyRef.current = nextKey;
    void trackEvent(identity, "input_quality_hint_shown", { hint_types: hintTypes });
  }, [identity, qualityHints]);

  const toBackendValues = (values: any) => ({
    ...values,
    packaging_level: packagingLevelMap[values.packaging_level] ?? values.packaging_level
  });

  const selectPackagingLevel = (value: string) => {
    form.setFieldValue("packaging_level", value);
    localStorage.setItem(draftKeys.packaging_level, value);
    void trackEvent(identity, "change_packaging_level", {
      display_level: value,
      mapped_level: packagingLevelMap[value] ?? value
    });
  };

  const fillTemplate = (type: string, text: string) => {
    const current = form.getFieldValue("raw_input")?.trim();
    const nextValue = current ? `${current}\n\n${text}` : text;
    form.setFieldValue("raw_input", nextValue);
    localStorage.setItem(draftKeys.raw_input, nextValue);
    void trackEvent(identity, "fill_example_template", { template_type: type });
    message.success(`已加入${type}模板`);
  };

  const onFinish = async (values: any) => {
    const backendValues = toBackendValues(values);
    setGenerating(true);
    setLastRequest(backendValues);
    void trackEvent(identity, "submit_experience", {
      ...backendValues,
      display_packaging_level: values.packaging_level
    });
    try {
      const result = await generateExperience(identity, backendValues);
      void trackEvent(identity, "generate_success", {
        generation_result_id: result.generation_result_id,
        completeness_score: result.result.completeness_score
      });
      setGeneration(result);
      message.success("生成完成");
    } catch (error) {
      void trackEvent(identity, "generate_failed", { message: String(error) });
      message.error(`生成失败：${String(error).slice(0, 80)}`);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <Card className="panel input-panel" title="经历输入">
      <Form
        form={form}
        layout="vertical"
        initialValues={initialValues}
        onFinish={onFinish}
        onValuesChange={(changedValues) => {
          const values = form.getFieldsValue();
          if (Object.prototype.hasOwnProperty.call(changedValues, "raw_input")) {
            localStorage.setItem(draftKeys.raw_input, values.raw_input || "");
          }
          if (Object.prototype.hasOwnProperty.call(changedValues, "target_role")) {
            localStorage.setItem(draftKeys.target_role, values.target_role || "");
          }
          if (Object.prototype.hasOwnProperty.call(changedValues, "packaging_level")) {
            localStorage.setItem(draftKeys.packaging_level, values.packaging_level || "");
          }
          if (Object.prototype.hasOwnProperty.call(changedValues, "experience_type")) {
            localStorage.setItem(draftKeys.experience_type, values.experience_type || "");
          }
          if (changedValues.packaging_level) {
            void trackEvent(identity, "change_packaging_level", {
              display_level: changedValues.packaging_level,
              mapped_level: packagingLevelMap[changedValues.packaging_level] ?? changedValues.packaging_level
            });
          }
          if (changedValues.target_role) {
            void trackEvent(identity, "change_target_role", { target_role: changedValues.target_role });
          }
        }}
      >
        <Form.Item label="目标岗位" name="target_role" rules={[{ required: true }]}>
          <Select options={targetRoles.map((value) => ({ value }))} />
        </Form.Item>
        <Form.Item label="使用模式" name="mode">
          <Radio.Group
            options={[
              { label: "包装一段经历", value: "single_experience" },
              { label: "生成完整简历", value: "full_resume" }
            ]}
          />
        </Form.Item>
        <Form.Item name="packaging_level" hidden>
          <Input />
        </Form.Item>
        <Form.Item label="包装强度">
          <div className="level-options">
            {packagingLevels.map((item) => (
              <button
                type="button"
                key={item.value}
                className={item.value === packagingLevel ? "level-option active" : "level-option"}
                aria-pressed={item.value === packagingLevel}
                onClick={() => selectPackagingLevel(item.value)}
              >
                <strong>{item.label}</strong>
                <p>{item.description}</p>
              </button>
            ))}
          </div>
        </Form.Item>
        <Form.Item label="经历类型" name="experience_type">
          <Select options={["项目", "实习", "开源", "比赛", "校园", "其他"].map((value) => ({ value }))} />
        </Form.Item>

        <div className="writing-guide">
          <div>
            <Typography.Title level={4}>建议这样写</Typography.Title>
            <p>不用写得很正式，按这个格式把关键信息补齐就够了。</p>
          </div>
          <div className="writing-format">
            {writingFormat.map((item, index) => (
              <p key={item}><span>{index + 1}</span>{item}</p>
            ))}
          </div>
        </div>

        <div className="experience-editor">
          <div className="editor-head">
            <div>
              <Typography.Title level={4}>原始经历描述</Typography.Title>
              <p>可以直接写，也可以先选择一个模板再修改。</p>
            </div>
            <div className="template-stack">
              <Space wrap className="template-actions">
                {exampleTemplates.map((item) => (
                  <Button key={item.type} onClick={() => fillTemplate(item.type, item.text)}>
                    {item.type}
                  </Button>
                ))}
              </Space>
              <span className="template-hint">选择一个模板吧~</span>
            </div>
          </div>
          <Form.Item name="raw_input" rules={[{ required: true, min: 10 }]}>
            <Input.TextArea autoSize={{ minRows: 5, maxRows: 14 }} placeholder="直接写你的项目、实习、比赛、开源经历即可。" />
          </Form.Item>
          <Alert
            className="privacy-reminder"
            type="info"
            showIcon
            message="隐私提醒：请勿输入身份证号、家庭住址、银行卡号、账号密码等敏感信息。手机号、邮箱等联系方式建议在最终简历下载后自行补充。"
          />
        </div>

        {qualityHints.length > 0 && (
          <div className="quality-hints">
            <strong>可以再补一点</strong>
            <div>
              {qualityHints.map((item) => <span key={item.type}>{item.text}</span>)}
            </div>
          </div>
        )}

        <Button type="primary" htmlType="submit" size="large" loading={generating}>
          {generating ? "正在生成，请稍等" : "生成包装与面试承接"}
        </Button>
      </Form>
    </Card>
  );
}
