from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.experience_segmentation_service import split_experience_segments  # noqa: E402
from app.services.semantic_experience_segmentation_service import segment_semantic_experiences  # noqa: E402


MIXED_INPUT = (
    "我是大二学生，利用 AI 做过一个回归分析计算器，可以智能检测数据本身合理性，"
    "包含不同的回归分析函数选择，能对应生成图像并综合回归分析效果；"
    "参加过学校校庆活动策划和执行，是某金奖实践队的重要任务参与者，主要负责实践落地和宣传联系；"
    "参与学校梦拓计划，深度参与学院晚会和专场演出的节目安排、审核与表演；"
    "担任学校足球协会的拍摄剪辑宣传；"
    "作为团队核心成员设计了智能停车场系统，根据路线、天气和车流情况提供停车指引，"
    "在路演中取得一等奖，希望包装得更适合 AI Agent 开发岗位。"
)

REALISTIC_COMMA_MIXED_INPUT = (
    "我是大二学生，利用 AI 做过一个回归分析计算器，可以智能检测数据本身合理性，"
    "包含不同的回归分析函数选择，能对应生成图像并综合回归分析效果；"
    "参加过学校校庆活动策划和执行，是某金奖实践队的重要任务参与者主要负责实践落地和宣传联系，"
    "参与学校梦拓计划，深度参与学院晚会，各项专场演出的节目安排、审核与表演，"
    "担任学校足球协会的拍摄剪辑宣传能力，作为团队核心成员设计了智能停车场系统，"
    "主要功能是根据路线和天气并考虑车流情况提供停车指引，在路演中取得一等奖，"
    "希望包装得更适合 AI Agent 开发岗位。"
)


def _joined(segment) -> str:
    return f"{segment.title} {segment.raw_text}"


def test_mixed_natural_language_is_split_into_distinct_experiences():
    result = segment_semantic_experiences(MIXED_INPUT)
    text_by_segment = [_joined(item) for item in result.segments]

    assert len(result.segments) >= 4
    assert any("回归分析计算器" in text for text in text_by_segment)
    assert any("校庆" in text or "实践队" in text for text in text_by_segment)
    assert any("足球协会" in text and "拍摄" in text for text in text_by_segment)
    assert any("智能停车场" in text and "一等奖" in text for text in text_by_segment)


def test_comma_connected_mixed_input_is_semantically_split():
    result = segment_semantic_experiences(REALISTIC_COMMA_MIXED_INPUT)
    text_by_segment = [_joined(item) for item in result.segments]

    assert len(result.segments) >= 4
    assert any("回归分析计算器" in text for text in text_by_segment)
    assert any("足球协会" in text and "拍摄剪辑" in text for text in text_by_segment)
    assert any("智能停车场" in text and "一等奖" in text for text in text_by_segment)
    parking = next(text for text in text_by_segment if "智能停车场" in text)
    assert "拍摄剪辑" not in parking


def test_project_features_are_not_over_segmented():
    raw = "利用 AI 做过一个回归分析计算器，可以检测数据合理性，包含回归函数选择，支持生成图像并综合分析效果。"
    result = segment_semantic_experiences(raw)

    assert len(result.segments) == 1
    assert "函数选择" in result.segments[0].raw_text
    assert "生成图像" in result.segments[0].raw_text


def test_parking_features_and_award_stay_together():
    raw = "作为团队核心成员设计智能停车场系统，根据路线、天气和车流提供停车指引，在路演中取得一等奖。"
    result = segment_semantic_experiences(raw)

    assert len(result.segments) == 1
    assert "路线" in result.segments[0].raw_text
    assert "一等奖" in result.segments[0].raw_text


def test_background_and_job_intent_do_not_become_projects():
    result = segment_semantic_experiences(MIXED_INPUT)
    body = " ".join(item.raw_text for item in result.segments)

    assert "我是大二学生" not in body
    assert "希望包装得更适合 AI Agent 开发岗位" not in body


def test_award_and_media_responsibility_do_not_cross_segments():
    result = segment_semantic_experiences(MIXED_INPUT)
    parking = next(item for item in result.segments if "智能停车场" in item.raw_text)
    media = next(item for item in result.segments if "足球协会" in item.raw_text)

    assert "一等奖" in parking.raw_text
    assert "拍摄剪辑" not in parking.raw_text
    assert "拍摄剪辑" in media.raw_text
    assert "一等奖" not in media.raw_text


def test_short_uncertain_input_is_not_over_segmented():
    result = segment_semantic_experiences("参加过活动，负责整理材料，也做了现场协助。")
    assert len(result.segments) == 1


def test_explicit_markdown_headings_keep_priority():
    raw = """### 项目一｜RAG 助手
实现文档检索与问答。

### 竞赛经历｜智能停车场
负责停车指引设计并获得一等奖。
"""
    segments = split_experience_segments(raw)

    assert len(segments) == 2
    assert segments[0].title == "RAG 助手"
    assert segments[1].title == "智能停车场"


if __name__ == "__main__":
    test_mixed_natural_language_is_split_into_distinct_experiences()
    test_comma_connected_mixed_input_is_semantically_split()
    test_project_features_are_not_over_segmented()
    test_parking_features_and_award_stay_together()
    test_background_and_job_intent_do_not_become_projects()
    test_award_and_media_responsibility_do_not_cross_segments()
    test_short_uncertain_input_is_not_over_segmented()
    test_explicit_markdown_headings_keep_priority()
    print("semantic experience segmentation tests passed")
