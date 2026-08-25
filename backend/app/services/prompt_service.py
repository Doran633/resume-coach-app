from pathlib import Path

from .. import schemas
from .experience_segmentation_service import build_experience_context
from .experience_identity_service import build_experience_identity_context
from .experience_identity_service import build_segmentation_questions
from .long_input_service import LongInputContext


BASE_DIR = Path(__file__).resolve().parents[3]
PROMPTS_DIR = BASE_DIR / "prompts"


def load_prompt(name: str) -> str:
    prompt_path = PROMPTS_DIR / name
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def build_generation_prompt(request: schemas.GenerateRequest, long_input_context: LongInputContext | None = None) -> str:
    segmentation_questions = build_segmentation_questions(request.raw_input)
    segmentation_question_context = "\n".join(f"- {item}" for item in segmentation_questions) or "无低置信度分段追问。"
    if long_input_context and long_input_context.long_input_mode:
        template = load_prompt("generate_resume_coach_result_long.md")
        return template.format(
            target_role=request.target_role,
            mode=request.mode,
            packaging_level=request.packaging_level,
            experience_type=request.experience_type,
            compact_experience_context=long_input_context.compact_context,
            experience_identity_context=build_experience_identity_context(request.raw_input),
            segmentation_question_context=segmentation_question_context,
        )

    template = load_prompt("generate_resume_coach_result.md")
    return template.format(
        target_role=request.target_role,
        mode=request.mode,
        packaging_level=request.packaging_level,
        experience_type=request.experience_type,
        raw_input=long_input_context.raw_input_for_prompt if long_input_context else request.raw_input,
        experience_context=build_experience_context(request.raw_input),
        experience_identity_context=build_experience_identity_context(request.raw_input),
        segmentation_question_context=segmentation_question_context,
    )
