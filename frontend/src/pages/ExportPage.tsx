import { Button, Card, Form, Input, Radio, Space, Typography, message } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { buildApiUrl, createDocx, submitFeedback, trackEvent } from "../api/client";
import { useAppStore } from "../store/appStore";
import { buildInterviewPreparation, formatInterviewItems, type InterviewGroupKey, type InterviewPreparationItem } from "../utils/interviewPreparation";

const groupConfig: Array<{ key: InterviewGroupKey; title: string; description: string }> = [
  { key: "questions", title: "面试问题", description: "提前梳理面试官可能追问的细节和回答重点。" },
  { key: "knowledge", title: "技术知识补齐", description: "围绕简历中的技术表达补齐原理、选型和实现细节。" },
  { key: "evidence", title: "证据材料准备", description: "核对日志、仓库、截图、指标和文档等事实材料。" },
  { key: "boundary", title: "表达边界", description: "不是让你删掉亮点，而是提前准备事实口径和降级说法。" }
];

export default function ExportPage() {
  const { generation, identity, setStep } = useAppStore();
  const [docxLoading, setDocxLoading] = useState(false);
  const [docxGenerated, setDocxGenerated] = useState(false);
  const [downloadStarted, setDownloadStarted] = useState(false);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<InterviewGroupKey>>(new Set());
  const feedbackSectionRef = useRef<HTMLDivElement | null>(null);
  const feedbackViewedRef = useRef(false);
  const feedbackStartedRef = useRef(false);
  const groups = useMemo(() => buildInterviewPreparation(generation?.result), [generation?.result]);
  const visibleGroups = groupConfig.filter((group) => groups[group.key].length > 0);
  const totalItems = visibleGroups.reduce((total, group) => total + groups[group.key].length, 0);

  useEffect(() => {
    if (!generation || totalItems === 0) return;
    void trackEvent(identity, "view_export_interview_plan", { generation_result_id: generation.generation_result_id, item_count: totalItems });
  }, [generation, identity, totalItems]);

  useEffect(() => {
    const element = feedbackSectionRef.current;
    if (!generation || !element) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting || feedbackViewedRef.current) return;
      feedbackViewedRef.current = true;
      void trackEvent(identity, "view_feedback_section", {
        generation_result_id: generation.generation_result_id
      });
      observer.disconnect();
    }, { threshold: 0.25 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [generation, identity]);

  if (!generation) return null;

  const copyText = async (text: string, successText: string) => {
    await navigator.clipboard.writeText(text);
    message.success(successText);
  };

  const copyGroup = async (key: InterviewGroupKey, title: string, items: InterviewPreparationItem[]) => {
    await copyText(formatInterviewItems(title, items), "本组内容已复制");
    await trackEvent(identity, "copy_interview_group", { group_type: key, item_count: items.length });
  };

  const copyAll = async () => {
    const content = visibleGroups.map((group) => formatInterviewItems(group.title, groups[group.key])).join("\n\n");
    await copyText(content, "全部面试准备已复制");
    await trackEvent(identity, "copy_all_interview_plan", { total_item_count: totalItems });
  };

  const toggleGroup = async (key: InterviewGroupKey) => {
    const next = new Set(expandedGroups);
    const willExpand = !next.has(key);
    willExpand ? next.add(key) : next.delete(key);
    setExpandedGroups(next);
    if (willExpand) await trackEvent(identity, "expand_interview_group", { group_type: key });
  };

  const generateDocx = async () => {
    setDocxLoading(true);
    try {
      await trackEvent(identity, "download_docx_started", { generation_result_id: generation.generation_result_id });
      const file = await createDocx(identity, generation.generation_result_id);
      setDocxGenerated(true);
      await trackEvent(identity, "generate_docx", { file_id: file.file_id });
      const link = document.createElement("a");
      link.href = buildApiUrl(file.download_url);
      link.download = file.file_name;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setDownloadStarted(true);
      await trackEvent(identity, "download_docx", { file_id: file.file_id });
      message.success("DOCX 已开始下载");
    } catch (error) {
      await trackEvent(identity, "download_docx_failed", { generation_result_id: generation.generation_result_id, message: String(error) });
      message.error("下载失败，请稍后重试");
    } finally {
      setDocxLoading(false);
    }
  };

  const onFinish = async (values: { model_comparison: "明显更好" | "略好一些" | "差不多" | "不如直接用大模型"; value_choice: "0元" | "2.99元" | "9.99元"; comment?: string }) => {
    setFeedbackSubmitting(true);
    try {
      await submitFeedback(identity, { generation_result_id: generation.generation_result_id, ...values });
      await trackEvent(identity, "submit_feedback", {
        ...values,
        has_comment: Boolean(values.comment?.trim()),
        docx_generated: docxGenerated,
        docx_download_started: downloadStarted
      });
      message.success("感谢您的真实反馈，我们会认真看。");
    } catch (error) {
      message.error(`评价提交失败：${String(error).slice(0, 60)}`);
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  const markFeedbackStarted = () => {
    if (feedbackStartedRef.current) return;
    feedbackStartedRef.current = true;
    void trackEvent(identity, "start_feedback", {
      generation_result_id: generation.generation_result_id,
      docx_generated: docxGenerated,
      docx_download_started: downloadStarted
    });
  };

  return (
    <Space direction="vertical" size="large" className="wide export-page">
      <Card className="panel export-result-status" title="先导出并查看简历">
        <div className="delivery-status-row">
          <span className={downloadStarted ? "delivery-status-dot is-ready" : "delivery-status-dot"} />
          <p>简历正文和面试准备内容已经整理完成。您可以先下载查看，再下拉分享您的使用体验。</p>
        </div>
      </Card>

      <Card className="panel export-hero" title="下载正式简历">
        <Typography.Paragraph>生成的 DOCX 只包含正式简历正文。姓名、联系方式、照片和未提供的教育信息会保留为待填写占位，不包含面试准备或系统建议。</Typography.Paragraph>
        <Typography.Paragraph className="export-note">下载后补充个人信息，并检查时间、学校和联系方式，即可作为初步投递版本使用。</Typography.Paragraph>
        <Space wrap>
          <Button onClick={() => setStep(1)}>返回查看结果</Button>
          <Button type="primary" loading={docxLoading} onClick={generateDocx}>{docxLoading ? "正在生成 DOCX" : "生成并下载 DOCX"}</Button>
        </Space>
      </Card>

      <Card className="panel interview-delivery" title="面试准备方案" extra={totalItems > 0 ? <Button onClick={copyAll}>复制全部</Button> : null}>
        <Typography.Paragraph>简历负责投递，这份方案帮助你接住简历里的强表达。</Typography.Paragraph>
        {visibleGroups.length ? (
          <div className="interview-plan-groups">
            {visibleGroups.map((group) => {
              const items = groups[group.key];
              const expanded = expandedGroups.has(group.key);
              const shownItems = expanded ? items : items.slice(0, 4);
              return (
                <section className="interview-plan-group" key={group.key}>
                  <div className="interview-plan-heading">
                    <div><h3>{group.title}</h3><p>{group.description}</p></div>
                    <Button onClick={() => copyGroup(group.key, group.title, items)}>复制本组</Button>
                  </div>
                  <ol className="interview-plan-list">
                    {shownItems.map((item, index) => <li key={`${group.key}-${index}-${item.text}`}><span>{item.text}</span>{item.note && <small>{item.note}</small>}</li>)}
                  </ol>
                  {items.length > 4 && <Button type="text" className="expand-plan-button" onClick={() => toggleGroup(group.key)}>{expanded ? "收起" : `查看其余 ${items.length - 4} 条`}</Button>}
                </section>
              );
            })}
          </div>
        ) : <p className="empty-hint">当前还没有生成面试准备内容，可以返回结果页补充经历细节后重新生成。</p>}
      </Card>

      <div ref={feedbackSectionRef} className="feedback-section-anchor">
        <Card className="panel service-feedback-panel">
          <div className="feedback-invitation">
            <Typography.Title level={3}>愿意和我们说说使用感受吗？</Typography.Title>
            <p>您是否愿意为我们的服务留下简单的评价？您的建议是我们继续改进的动力。</p>
            <small>只需要选择两个选项，也可以补充一两句真实感受。</small>
          </div>
          <Form layout="vertical" onFinish={onFinish} onValuesChange={markFeedbackStarted}>
            <Form.Item label="你认为这个服务相比当前市场大模型效果如何？" name="model_comparison" rules={[{ required: true }]}><Radio.Group options={["明显更好", "略好一些", "差不多", "不如直接用大模型"].map((value) => ({ label: value, value }))} /></Form.Item>
            <Form.Item label="你认为这样的服务价值多少？" name="value_choice" rules={[{ required: true }]}><Radio.Group options={["0元", "2.99元", "9.99元"].map((value) => ({ label: value, value }))} /></Form.Item>
            <Form.Item label="还有什么想告诉我们？" name="comment"><Input.TextArea rows={4} placeholder="可以写下觉得好用的地方、遇到的问题，或者希望我们增加的能力。" /></Form.Item>
            <Button type="primary" htmlType="submit" loading={feedbackSubmitting}>提交评价</Button>
          </Form>
        </Card>
      </div>
    </Space>
  );
}
