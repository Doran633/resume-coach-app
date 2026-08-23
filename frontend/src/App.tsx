import { Layout, Steps } from "antd";
import { useEffect } from "react";
import InputPage from "./pages/InputPage";
import ResultPage from "./pages/ResultPage";
import ExportPage from "./pages/ExportPage";
import { trackEvent } from "./api/client";
import { useAppStore } from "./store/appStore";

const { Header, Content } = Layout;

export default function App() {
  const { step, identity } = useAppStore();

  useEffect(() => {
    trackEvent(identity, "visit_home");
  }, [identity]);

  return (
    <Layout className="app-shell">
      <Header className="topbar">
        <div>
          <strong>Resume Coach v0.1</strong>
          <span>AI 求职教练 · 经历包装 · 面试承接</span>
        </div>
      </Header>
      <Content className="content">
        <section className="intro">
          <h1>不是普通简历润色，而是判断你的经历能写多强</h1>
          <p>输入一段经历，生成普通版、大胆版、边界参考、Claim 风险和面试知识补齐。v0.1 支持 mock / 真实 LLM 双模式。</p>
        </section>
        <Steps
          className="steps"
          current={step}
          items={[
            { title: "输入经历" },
            { title: "查看包装" },
            { title: "导出反馈" }
          ]}
        />
        {step === 0 && <InputPage />}
        {step === 1 && <ResultPage />}
        {step === 2 && <ExportPage />}
      </Content>
    </Layout>
  );
}
