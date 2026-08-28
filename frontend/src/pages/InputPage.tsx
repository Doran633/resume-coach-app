import { Alert, Button, Card, Form, Input, Select, Space, Spin, Typography, message } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { generateExperience, trackEvent } from "../api/client";
import { useAppStore } from "../store/appStore";
import { getGenerationErrorInfo, type GenerationErrorInfo } from "../utils/errorMessages";

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

const generationStages = [
  { delay: 0, key: "reading", text: "正在读取并拆分您的经历" },
  { delay: 4000, key: "boundary", text: "正在识别岗位重点和事实边界" },
  { delay: 9000, key: "writing", text: "正在生成不同强度的简历表达" },
  { delay: 16000, key: "quality", text: "正在检查重复内容和表达风险" },
  { delay: 24000, key: "resume", text: "正在整理正式简历与面试准备" },
  { delay: 35000, key: "long_input", text: "内容较多，正在继续处理，请稍等" },
  { delay: 60000, key: "slow_service", text: "本次生成耗时较长，可能与网络或模型服务有关，请继续保持页面打开" }
];

export default function InputPage() {
  const [form] = Form.useForm();
  const [generating, setGenerating] = useState(false);
  const [generationStage, setGenerationStage] = useState(generationStages[0]);
  const [generationError, setGenerationError] = useState<GenerationErrorInfo | null>(null);
  const [activeTemplate, setActiveTemplate] = useState("");
  const { identity, lastRequest, setGeneration, setLastRequest } = useAppStore();
  const packagingLevel = Form.useWatch("packaging_level", form) ?? "重点放大";
  const textAreaRef = useRef<any>(null);
  const templateFeedbackTimerRef = useRef<number | null>(null);
  const generationTimerRefs = useRef<number[]>([]);
  const generationInFlightRef = useRef(false);
  const retryingRef = useRef(false);
  const initialValues = useMemo(() => {
    const savedPackagingLevel = localStorage.getItem(draftKeys.packaging_level) || "重点放大";
    return {
      target_role: lastRequest?.target_role || localStorage.getItem(draftKeys.target_role) || "AI / 大模型 / Agent",
      packaging_level: lastRequest?.packaging_level
        ? packagingLevelDisplayMap[lastRequest.packaging_level] ?? lastRequest.packaging_level
        : packagingLevelDisplayMap[savedPackagingLevel] ?? savedPackagingLevel,
      raw_input: lastRequest?.raw_input || localStorage.getItem(draftKeys.raw_input) || ""
    };
  }, [lastRequest]);

  const clearGenerationTimers = () => {
    generationTimerRefs.current.forEach((timer) => window.clearTimeout(timer));
    generationTimerRefs.current = [];
  };

  useEffect(() => () => {
    if (templateFeedbackTimerRef.current !== null) {
      window.clearTimeout(templateFeedbackTimerRef.current);
    }
    clearGenerationTimers();
  }, []);

  const startGenerationStages = (inputLength: number) => {
    clearGenerationTimers();
    setGenerationStage(generationStages[0]);
    generationTimerRefs.current = generationStages.slice(1).map((stage) => window.setTimeout(() => {
      setGenerationStage(stage);
      if ([16000, 35000, 60000].includes(stage.delay)) {
        void trackEvent(identity, "generation_wait_stage", {
          stage: stage.key,
          elapsed_ms: stage.delay,
          input_length: inputLength
        });
      }
    }, stage.delay));
  };

  const toBackendValues = (values: any) => ({
    ...values,
    mode: "full_resume",
    experience_type: "综合经历",
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
    void trackEvent(identity, "fill_example_template", {
      template_type: type,
      action: "fill",
      had_existing_input: Boolean(current)
    });
    setActiveTemplate(type);
    if (templateFeedbackTimerRef.current !== null) {
      window.clearTimeout(templateFeedbackTimerRef.current);
    }
    templateFeedbackTimerRef.current = window.setTimeout(() => setActiveTemplate(""), 1200);
    message.success(`已填入${type}模板`);
    window.requestAnimationFrame(() => {
      textAreaRef.current?.focus({ cursor: "end" });
    });
  };

  const onFinish = async (values: any) => {
    if (generating || generationInFlightRef.current) return;
    generationInFlightRef.current = true;
    const backendValues = toBackendValues(values);
    const startedAt = Date.now();
    setGenerationError(null);
    setGenerating(true);
    startGenerationStages(backendValues.raw_input.length);
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
      message.success("生成完成，正在为您展示结果。");
    } catch (error) {
      const errorInfo = getGenerationErrorInfo(error);
      setGenerationError(errorInfo);
      if (import.meta.env.DEV) console.error(error);
      void trackEvent(identity, "generate_failed", {
        error_type: errorInfo.type,
        elapsed_ms: Date.now() - startedAt,
        input_length: backendValues.raw_input.length,
        has_multiple_experiences: /\n\s*\n|项目[一二三四五]|经历[一二三四五]|实习经历|科研经历|竞赛经历/.test(backendValues.raw_input)
      });
    } finally {
      clearGenerationTimers();
      generationInFlightRef.current = false;
      setGenerating(false);
      retryingRef.current = false;
    }
  };

  const retryGeneration = () => {
    if (generating || retryingRef.current) return;
    retryingRef.current = true;
    const rawInput = String(form.getFieldValue("raw_input") || "");
    void trackEvent(identity, "retry_generation", {
      error_type: generationError?.type || "unknown",
      input_length: rawInput.length
    });
    form.submit();
  };

  return (
    <Card className="panel input-panel" title="经历输入">
      <Form
        form={form}
        layout="vertical"
        initialValues={initialValues}
        onFinish={onFinish}
        onValuesChange={(changedValues) => {
          if (generationError) setGenerationError(null);
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
            </div>
            <div className="template-stack">
              <Space wrap className="template-actions">
                {exampleTemplates.map((item) => (
                  <Button
                    key={item.type}
                    className={activeTemplate === item.type ? "template-button is-filled" : "template-button"}
                    aria-label={`填入${item.type}模板`}
                    onClick={() => fillTemplate(item.type, item.text)}
                  >
                    {activeTemplate === item.type ? "已填入" : item.type}
                  </Button>
                ))}
              </Space>
              <span className="template-label">点击模板快速填入</span>
            </div>
          </div>
          <Form.Item name="raw_input" rules={[{ required: true, min: 10 }]}>
            <Input.TextArea
              ref={textAreaRef}
              autoSize={{ minRows: 5, maxRows: 14 }}
              placeholder="选择一个模板，或直接输入您的项目 / 实习 / 科研 / 开源经历。"
            />
          </Form.Item>
          <Alert
            className="privacy-reminder"
            type="info"
            showIcon
            message="隐私提醒：请勿输入身份证号、家庭住址、银行卡号、账号密码等敏感信息。手机号、邮箱等联系方式建议在最终简历下载后自行补充。"
          />
        </div>

        {generating && (
          <div className="generation-status" role="status" aria-live="polite">
            <Spin size="small" />
            <div>
              <strong>{generationStage.text}</strong>
              <p>{generationStage.delay >= 35000
                ? "您可以保持当前页面打开，系统完成后会自动展示结果。"
                : "长输入或多段经历可能需要更长时间，请不要关闭页面。"}</p>
            </div>
          </div>
        )}

        {generationError && (
          <div className="generation-error" role="alert">
            <div>
              <strong>这次没有生成成功</strong>
              <p>{generationError.message}</p>
              <small>您可以检查或修改输入，也可以直接使用当前内容重新生成。</small>
            </div>
            <Button className="retry-generation-button" onClick={retryGeneration}>重新生成</Button>
          </div>
        )}

        <Button type="primary" htmlType="submit" size="large" loading={generating} disabled={generating}>
          {generating ? "正在生成简历内容" : "生成包装与面试承接"}
        </Button>
      </Form>
    </Card>
  );
}
