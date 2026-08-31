import { Button, message } from "antd";

export default function SupportCode({
  requestId,
  onCopy
}: {
  requestId?: string;
  onCopy?: (requestId: string) => void | Promise<void>;
}) {
  if (!requestId) {
    return <span className="support-code-unavailable">暂未生成问题编号</span>;
  }
  const copy = async () => {
    await navigator.clipboard.writeText(requestId);
    await onCopy?.(requestId);
    message.success("问题编号已复制");
  };
  return (
    <span className="support-code">
      问题编号：<code>{requestId}</code>
      <Button type="link" size="small" onClick={copy}>复制编号</Button>
    </span>
  );
}
