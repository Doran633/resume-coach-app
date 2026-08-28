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
          <strong>简历教练</strong>
        </div>
      </Header>
      <Content className="content">
        <section className="intro">
          <h1>简历教练</h1>
          <p>——把你的经历写出彩</p>
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
