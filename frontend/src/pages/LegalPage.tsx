import { Alert, Button, Card, Modal, Space, Typography, message } from "antd";
import { useState } from "react";
import { deleteMyData } from "../api/client";
import { useAppStore } from "../store/appStore";


export type LegalPageKey = "privacy" | "terms" | "ai";

const effectiveDate = "2026-08-31";
const version = "v0.7.2";
const retentionDays = import.meta.env.VITE_USER_CONTENT_RETENTION_DAYS || "30";
const contactEmail = import.meta.env.VITE_PRIVACY_CONTACT_EMAIL || "";
const providerName = import.meta.env.VITE_AI_PROVIDER_NAME || "第三方大模型服务商";

function ContactLine() {
  return contactEmail
    ? <p>隐私联系邮箱：<a href={`mailto:${contactEmail}`}>{contactEmail}</a></p>
    : <p>如需联系我们，可先通过导出页的服务反馈入口提交说明。</p>;
}

export default function LegalPage({ page, onBack }: { page: LegalPageKey; onBack: () => void }) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const resetAfterDataDeletion = useAppStore((state) => state.resetAfterDataDeletion);

  const confirmDelete = async () => {
    setDeleting(true);
    try {
      const result = await deleteMyData();
      resetAfterDataDeletion();
      setConfirmOpen(false);
      onBack();
      message.success(result.files_cleanup_pending
        ? "数据记录已删除，少量文件正在等待系统清理。"
        : "您的经历、生成结果和导出文件已删除。");
    } catch {
      message.error("数据删除失败，请稍后重试。现有内容不会被前端静默清空。");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Space direction="vertical" size="large" className="wide legal-page">
      <Button className="legal-back" onClick={onBack}>返回简历教练</Button>

      {page === "privacy" && (
        <Card className="panel legal-document" title="隐私政策">
          <Typography.Paragraph>生效日期：{effectiveDate}　版本：{version}</Typography.Paragraph>
          <Typography.Title level={3}>我们处理哪些数据</Typography.Title>
          <Typography.Paragraph>为了完成简历生成、结果展示、DOCX 导出、故障定位和服务改进，我们会处理您主动提交的经历描述、目标岗位、生成结果、匿名 Cookie、会话标识、必要的调用状态、用于防滥用的脱敏 IP 哈希以及您主动提交的反馈。我们不在运营报告中保存原始 IP。</Typography.Paragraph>
          <Typography.Title level={3}>处理目的与第三方服务</Typography.Title>
          <Typography.Paragraph>经历内容用于生成和校验简历。生成过程中可能由 {providerName} 提供模型推理能力，因此请不要提交身份证号、家庭住址、银行卡号、账号密码或无权处理的他人信息。</Typography.Paragraph>
          <Typography.Title level={3}>保存期限</Typography.Title>
          <Typography.Paragraph>经历输入和生成结果默认保存 {retentionDays} 天，DOCX 默认保存 7 天，脱敏运营记录默认保存 90 天，受限访问的数据库备份默认保存 14 天；法律法规或安全审计另有要求时，以必要范围内的期限为准。</Typography.Paragraph>
          <Typography.Title level={3}>匿名 Cookie</Typography.Title>
          <Typography.Paragraph>服务端签名 Cookie 用于识别当前浏览器、保护生成结果和下载文件的访问权限，不用于跨站广告追踪。清除浏览器 Cookie 后，您可能无法继续访问此前生成的内容。</Typography.Paragraph>
          <Typography.Title level={3}>您的选择</Typography.Title>
          <Typography.Paragraph>您可以在下方删除当前匿名身份对应的经历、生成结果、会话和导出文件。在线数据删除后无法恢复，也不会影响其他用户的数据；受限备份中的历史副本仅用于灾难恢复，并会在最长 14 天的备份保留期内到期清理。</Typography.Paragraph>
          <ContactLine />
          <Alert type="warning" showIcon message="删除前请先下载需要保留的 DOCX。删除完成后，当前浏览器中的草稿和结果也会被清空。" />
          <Button danger className="delete-data-button" onClick={() => setConfirmOpen(true)}>删除我的数据</Button>
        </Card>
      )}

      {page === "terms" && (
        <Card className="panel legal-document" title="服务条款">
          <Typography.Paragraph>生效日期：{effectiveDate}　版本：{version}</Typography.Paragraph>
          <Typography.Title level={3}>服务范围</Typography.Title>
          <Typography.Paragraph>简历教练根据用户提供的经历生成简历表达、事实风险提示和面试准备内容。服务结果是辅助材料，不构成录用、职业资格或招聘结果保证。</Typography.Paragraph>
          <Typography.Title level={3}>用户责任</Typography.Title>
          <Typography.Paragraph>您应确保提交内容真实、合法且有权处理，并在投递前核验公司、岗位、时间、技术、指标和奖项等事实。不得利用本服务伪造经历、侵犯他人权益或制作违法内容。</Typography.Paragraph>
          <Typography.Title level={3}>服务可用性</Typography.Title>
          <Typography.Paragraph>模型和网络服务可能出现排队、超时或暂时不可用。我们会通过限流、备份和健康检查提高稳定性，但不承诺服务永不中断。</Typography.Paragraph>
          <Typography.Title level={3}>内容使用</Typography.Title>
          <Typography.Paragraph>您可以将生成结果用于个人求职准备。正式使用前应根据自身真实经历修改，不应将无法解释或无法证明的内容作为事实对外陈述。</Typography.Paragraph>
          <ContactLine />
        </Card>
      )}

      {page === "ai" && (
        <Card className="panel legal-document" title="AI 辅助生成说明">
          <Typography.Paragraph>生效日期：{effectiveDate}　版本：{version}</Typography.Paragraph>
          <Typography.Title level={3}>AI 如何参与</Typography.Title>
          <Typography.Paragraph>系统使用 AI 对经历进行分段、岗位化表达和结构整理，并通过确定性规则检查事实边界、重复内容、异常字符和无证据技能。</Typography.Paragraph>
          <Typography.Title level={3}>AI 的边界</Typography.Title>
          <Typography.Paragraph>自动生成仍可能出现遗漏、误解或不准确表达。页面结果和 DOCX 均需要由您核验，尤其是量化指标、公司岗位、上线状态、获奖情况和技术职责。</Typography.Paragraph>
          <Typography.Title level={3}>关于生成内容标识</Typography.Title>
          <Typography.Paragraph>本服务会在网页交互中明确说明内容由 AI 辅助生成。对于导出文件的显式、隐式标识及无显式标识导出条件，我们会依据适用规则和专业意见持续完善，不以自创元数据替代正式标准。</Typography.Paragraph>
          <Typography.Title level={3}>合理使用</Typography.Title>
          <Typography.Paragraph>AI 负责帮助组织表达，事实仍应来自您本人。请保留能够支撑简历内容的仓库、文档、日志、证书、截图或数据口径。</Typography.Paragraph>
          <ContactLine />
        </Card>
      )}

      <Modal
        title="确认删除当前匿名数据？"
        open={confirmOpen}
        confirmLoading={deleting}
        okText="确认删除"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        onOk={confirmDelete}
        onCancel={() => !deleting && setConfirmOpen(false)}
        closable={!deleting}
        maskClosable={!deleting}
      >
        <p>这会删除当前浏览器身份对应的经历输入、生成结果、会话和 DOCX 文件，操作无法撤销。</p>
      </Modal>
    </Space>
  );
}
