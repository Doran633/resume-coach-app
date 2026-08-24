from pathlib import Path

from .. import schemas
from .experience_segmentation_service import build_experience_context


BASE_DIR = Path(__file__).resolve().parents[3]
PROMPTS_DIR = BASE_DIR / "prompts"


def load_prompt(name: str) -> str:
    prompt_path = PROMPTS_DIR / name
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def build_generation_prompt(request: schemas.GenerateRequest) -> str:
    template = load_prompt("generate_resume_coach_result.md")
    return template.format(
        target_role=request.target_role,
        mode=request.mode,
        packaging_level=request.packaging_level,
        experience_type=request.experience_type,
        raw_input=request.raw_input,
        experience_context=build_experience_context(request.raw_input),
    )
