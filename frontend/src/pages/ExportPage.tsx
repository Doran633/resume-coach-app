import { Button, Card, Form, Input, Radio, Space, Typography, message } from "antd";
import { buildApiUrl, createDocx, submitFeedback, trackEvent } from "../api/client";
import { useAppStore } from "../store/appStore";

export default function ExportPage() {
  const { generation, identity, setStep } = useAppStore();

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
    <Space direction="vertical" size="large" className="wide">
      <Card className="panel" title="导出正式简历">
        <Typography.Paragraph>
          当前版本会根据推荐表达生成基础技术简历 DOCX，文件保存在后端 outputs 目录。
        </Typography.Paragraph>
        <Space>
          <Button onClick={() => setStep(1)}>返回结果</Button>
          <Button type="primary" onClick={generateDocx}>生成并下载 DOCX</Button>
        </Space>
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
