from typing import Any, Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["green", "yellow", "red", "black"]


class IdentityPayload(BaseModel):
    anonymous_user_id: str
    session_id: str


class EventCreate(IdentityPayload):
    event_name: str
    target_role: str | None = None
    mode: str | None = None
    packaging_level: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(IdentityPayload):
    target_role: str
    mode: Literal["single_experience", "full_resume"] = "single_experience"
    packaging_level: Literal["稳妥", "大胆", "极限"] = "大胆"
    experience_type: str
    raw_input: str


class ClaimResult(BaseModel):
    claim: str
    risk_level: RiskLevel
    evidence: str
    risk_reason: str = ""
    interview_questions: list[str]
    knowledge_to_prepare: list[str]
    downgrade_wording: str


class ResumeSections(BaseModel):
    personal_info: dict[str, str] = Field(default_factory=dict)
    summary: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    education: dict[str, str] = Field(default_factory=dict)
    interview_preparation: list[str] = Field(default_factory=list)


class GenerationPayload(BaseModel):
    completeness_score: int
    confirmed_facts: list[str]
    missing_questions: list[str]
    normal_version: str
    bold_version: str
    boundary_version: str
    recommended_version: str
    claims: list[ClaimResult]
    interview_plan: list[str]
    knowledge_checklist: list[str]
    resume_sections: ResumeSections


class GenerateResponse(BaseModel):
    experience_input_id: int
    generation_result_id: int
    result: GenerationPayload


class DocxCreate(IdentityPayload):
    generation_result_id: int
    version_type: Literal["normal", "bold", "boundary", "recommended"] = "recommended"


class DocxResponse(BaseModel):
    file_id: int
    file_name: str
    download_url: str


class FeedbackCreate(IdentityPayload):
    generation_result_id: int | None = None
    model_comparison: Literal["明显更好", "略好一些", "差不多", "不如直接用大模型"]
    value_choice: Literal["0元", "2.99元", "9.99元"]
    comment: str | None = None
