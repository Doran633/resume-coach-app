import { Alert, Layout, Steps } from "antd";
import { useEffect, useState } from "react";
import InputPage from "./pages/InputPage";
import ResultPage from "./pages/ResultPage";
import ExportPage from "./pages/ExportPage";
import LegalPage, { type LegalPageKey } from "./pages/LegalPage";
import { trackEvent } from "./api/client";
import { useAppStore } from "./store/appStore";

const { Header, Content, Footer } = Layout;

const legalPages = new Set<LegalPageKey>(["privacy", "terms", "ai"]);

function currentLegalPage(): LegalPageKey | null {
  const value = window.location.hash.replace(/^#\/?/, "") as LegalPageKey;
  return legalPages.has(value) ? value : null;
}

export default function App() {
  const { step, identity } = useAppStore();
  const [legalPage, setLegalPage] = useState<LegalPageKey | null>(currentLegalPage);

  useEffect(() => {
    const handleHashChange = () => setLegalPage(currentLegalPage());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

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
        {legalPage ? (
          <LegalPage page={legalPage} onBack={() => { window.location.hash = ""; }} />
        ) : (
          <>
            <Steps
              className="steps"
              current={step}
              items={[
                { title: "输入经历" },
                { title: "查看包装" },
                { title: "导出反馈" }
              ]}
            />
            {step === 1 && (
              <Alert className="ai-output-notice result-ai-notice" type="info" showIcon message="结果由 AI 辅助整理，请在使用前核验公司、岗位、时间、技术与指标等事实。" />
            )}
            {step === 0 && <InputPage />}
            {step === 1 && <ResultPage />}
            {step === 2 && <ExportPage />}
          </>
        )}
      </Content>
      <Footer className="site-footer">
        <nav aria-label="服务与隐私说明">
          <a href="#/privacy">隐私政策</a>
          <a href="#/terms">服务条款</a>
          <a href="#/ai">AI 辅助生成说明</a>
        </nav>
        <div className="filing-links">
          {import.meta.env.VITE_ICP_NUMBER && (
            <a href={import.meta.env.VITE_ICP_LINK || "https://beian.miit.gov.cn/"} target="_blank" rel="noreferrer">
              {import.meta.env.VITE_ICP_NUMBER}
            </a>
          )}
          {import.meta.env.VITE_PUBLIC_SECURITY_NUMBER && (
            <a href={import.meta.env.VITE_PUBLIC_SECURITY_LINK || "#"} target="_blank" rel="noreferrer">
              {import.meta.env.VITE_PUBLIC_SECURITY_NUMBER}
            </a>
          )}
        </div>
      </Footer>
    </Layout>
  );
}
