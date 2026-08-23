import { Alert, Button, Card, Form, Input, Radio, Select, message } from "antd";
import { useState } from "react";
import { generateExperience, trackEvent } from "../api/client";
import { useAppStore } from "../store/appStore";

const sample = "我是大二学生，做过一个 AI 复习辅助系统，使用 React、TypeScript、FastAPI、SQLite 和 RAG，支持资料上传、文档解析、知识检索和复习重点生成。有真实用户访问记录，也希望包装得更适合 AI Agent 开发岗位。";

export default function InputPage() {
  const [form] = Form.useForm();
  const [generating, setGenerating] = useState(false);
  const { identity, setGeneration, setLastRequest } = useAppStore();

  const onFinish = async (values: any) => {
    setGenerating(true);
    setLastRequest(values);
    void trackEvent(identity, "submit_experience", values);
    try {
      const result = await generateExperience(identity, values);
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
    <Card className="panel" title="经历输入">
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          target_role: "AI Agent",
          mode: "single_experience",
          packaging_level: "大胆",
          experience_type: "项目",
          raw_input: sample
        }}
        onFinish={onFinish}
      >
        <Form.Item label="目标岗位" name="target_role" rules={[{ required: true }]}>
          <Select
            options={["AI Agent", "大模型训练", "前端开发", "后端开发", "测试开发", "数据分析", "产品助理", "运营", "泛互联网岗位"].map((value) => ({ value }))}
          />
        </Form.Item>
        <Form.Item label="使用模式" name="mode">
          <Radio.Group
            options={[
              { label: "包装一段经历", value: "single_experience" },
              { label: "生成完整简历", value: "full_resume" }
            ]}
          />
        </Form.Item>
        <Form.Item label="包装强度" name="packaging_level">
          <Radio.Group options={["稳妥", "大胆", "极限"].map((value) => ({ label: value, value }))} />
        </Form.Item>
        <Form.Item label="经历类型" name="experience_type">
          <Select options={["项目", "实习", "开源", "比赛", "校园", "其他"].map((value) => ({ value }))} />
        </Form.Item>
        <Alert
          className="privacy-reminder"
          type="info"
          showIcon
          message="隐私提醒：请勿输入身份证号、家庭住址、银行卡号、账号密码等敏感信息。手机号、邮箱等联系方式建议在最终简历下载后自行补充。"
        />
        <Form.Item label="原始经历描述" name="raw_input" rules={[{ required: true, min: 10 }]}>
          <Input.TextArea rows={8} placeholder="请描述你做过什么、用了什么技术、有什么结果或证据。避免填写身份证号、家庭住址、银行卡号、账号密码等敏感信息。" />
        </Form.Item>
        <Button type="primary" htmlType="submit" size="large" loading={generating}>
          {generating ? "正在生成，请稍等" : "生成包装与面试承接"}
        </Button>
      </Form>
    </Card>
  );
}
