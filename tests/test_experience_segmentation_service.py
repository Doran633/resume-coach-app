from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.experience_segmentation_service import build_experience_context, split_experience_segments  # noqa: E402
from app.services.prompt_service import build_generation_prompt  # noqa: E402


LONG_INPUT = """项目一｜AI RAG 智能助手

从零设计并持续迭代一套可公网使用的 AI RAG 助手，使用 React + TypeScript、FastAPI、SQLite 完成前后端与数据持久化，实现文件上传解析、文本切块、BAAI/bge-m3 Embedding、向量检索、RAG 问答、Citation、连续对话与会话恢复。围绕 chunk、Top-K、阈值及检索排序进行了多轮量化优化，并搭建 Debug Trace、固定测试集和 Groundedness、Citation、Retrieval 等评测指标。工程侧完成匿名用户数据隔离、邀请码保护、日志、健康检查、Smoke Test，并解决旧进程、端口冲突、Embedding 配置、CORS 等实际联调问题，最终通过 VPS + Nginx + systemd 部署并上线独立域名。

### 项目二｜Resume Positioning Coach

独立设计并开发 AI 简历定位与包装网站，核心目标是将用户真实经历转化为“表达更强、但面试能够承接”的简历内容。设计“经历输入 → 信息完整度分析 → 岗位定位 → 三档包装 → Claim 承接检查 → 面试准备 → 简历生成 → DOCX 导出”的完整工作流，并通过风险分级识别缺乏事实支撑的夸大表达。根据真实用户测试持续优化产品：重构早期复杂按钮式 UI，形成更清晰的流程化交互；发现 LLM 虽满足 JSON Schema 但正式简历字段可能为空后，引入 Resume Section Fallback，在保存和导出前进行业务完整性检查。目前进一步发现多经历场景存在 Experience Dilution，正推进经历级拆分与分阶段生成以保持单段履历的信息密度。
"""


def test_split_experience_segments_supports_vertical_bar_headings():
    segments = split_experience_segments(LONG_INPUT)

    assert len(segments) == 2
    assert segments[0].label == "项目一"
    assert segments[0].title == "AI RAG 智能助手"
    assert segments[1].label == "项目二"
    assert segments[1].title == "Resume Positioning Coach"


def test_build_experience_context_guides_multi_project_generation():
    context = build_experience_context(LONG_INPUT)

    assert "系统预解析到 2 段主要经历" in context
    assert "AI RAG 智能助手" in context
    assert "Resume Positioning Coach" in context
    assert "不要因为输入较长而随意合并或删除" in context


def test_generation_prompt_contains_experience_context():
    prompt = build_generation_prompt(
        schemas.GenerateRequest(
            anonymous_user_id="u-test",
            session_id="s-test",
            target_role="AI / 大模型 / Agent",
            mode="full_resume",
            packaging_level="大胆",
            experience_type="项目经历",
            raw_input=LONG_INPUT,
        )
    )

    assert "系统预解析经历" in prompt
    assert "系统预解析到 2 段主要经历" in prompt
    assert "项目一｜AI RAG 智能助手" in prompt


def test_split_experience_segments_supports_non_project_types():
    raw = """### 实习经历｜字节跳动前端开发实习
参与内部后台页面开发、接口联调和缺陷修复。

科研经历：工业工程排程优化研究
整理文献、设计约束条件并完成实验报告。

竞赛经历-大学生创新创业训练项目
负责方案设计、答辩材料和展示。
"""
    segments = split_experience_segments(raw)

    assert len(segments) == 3
    assert segments[0].label == "实习经历"
    assert segments[0].title == "字节跳动前端开发实习"
    assert segments[1].label == "科研经历"
    assert segments[1].title == "工业工程排程优化研究"
    assert segments[2].label == "竞赛经历"
    assert segments[2].title == "大学生创新创业训练项目"


if __name__ == "__main__":
    test_split_experience_segments_supports_vertical_bar_headings()
    test_build_experience_context_guides_multi_project_generation()
    test_generation_prompt_contains_experience_context()
    test_split_experience_segments_supports_non_project_types()
    print("experience segmentation tests passed")
